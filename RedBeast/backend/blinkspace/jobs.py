"""Hazırlama işleri: HTTP isteğinin ömründen bağımsız, süreç içi işçi iş parçacığı.

Durumlar gerçek durumu yansıtır:
  queued → searching → downloading → preparing → done | insufficient_data | failed | cancelled

- Aynı isteği birleştirme: aynı `request_key` için bitmemiş iş varsa yeni iş açılmaz.
- Önbellek: aynı istek için taze bir dizi varsa iş anında `done` olarak döner.
- İptal: bayrak veritabanında tutulur; hat her adım arasında denetler.
- Zaman aşımı: hat `job_timeout_s` sonunda `failed/timeout` ile biter.
- Sunucu yeniden başlarsa yarım işler `failed/interrupted_by_restart` olarak işaretlenir.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from dataclasses import asdict

from .archive import ArchiveError
from .config import Settings
from .cutouts import CutoutError
from .db import TERMINAL, Database
from .pipeline import Cancelled, InsufficientData, Pipeline, SearchParams, new_id
from .spectrum import SpectrumParams, is_fresh, run_spectrum

log = logging.getLogger("blinkspace.jobs")
MAX_QUEUED = 12


class QueueFull(Exception):
    pass


class JobManager:
    def __init__(self, pipeline: Pipeline, db: Database, settings: Settings, workers: int = 1, autostart: bool = True):
        self.pipeline = pipeline
        self.db = db
        self.settings = settings
        self._q: "queue.Queue[str | None]" = queue.Queue()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._workers = workers
        self._stopping = False
        if autostart:
            self.start()

    def start(self) -> None:
        for i in range(self._workers):
            t = threading.Thread(target=self._loop, name=f"blinkspace-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self, timeout: float = 5.0) -> None:
        self._stopping = True
        for _ in self._threads:
            self._q.put(None)
        for t in self._threads:
            t.join(timeout)

    # ------------------------------------------------------------------ gönderim
    def submit(self, params: SearchParams, force_refresh: bool = False) -> dict:
        key = params.request_key()
        with self._lock:
            if not force_refresh:
                seq = self.db.latest_sequence_for(key, self.settings.tap_cache_hours * 3600.0)
                if seq is not None:
                    job_id = new_id(12)
                    self.db.create_job(job_id, key, "sequence", params.normalized())
                    self.db.update_job(job_id, status="done" if seq["status"] == "ready" else "insufficient_data",
                                       stage="done", progress=1.0, sequence_id=seq["id"], detail={"from_cache": True})
                    return self.public(self.db.get_job(job_id))
            active = self.db.active_job_for(key)
            # A job that is being cancelled is on its way out: asking again starts a fresh one behind it.
            if active is not None and not active["cancel_requested"]:
                return dict(self.public(active), merged=True)
            if self.db.count_active_jobs() >= MAX_QUEUED:
                raise QueueFull()
            job_id = new_id(12)
            self.db.create_job(job_id, key, "sequence", params.normalized())
            self._q.put(job_id)
            return self._with_queue(self.db.get_job(job_id))

    def submit_spectrum(self, params: SpectrumParams) -> dict:
        key = params.request_key()
        with self._lock:
            if is_fresh(self.settings, key):
                job_id = new_id(12)
                self.db.create_job(job_id, key, "spectrum", params.normalized())
                self.db.update_job(job_id, status="done", stage="done", progress=1.0, sequence_id=key, detail={"from_cache": True})
                return self.public(self.db.get_job(job_id))
            active = self.db.active_job_for(key)
            # A job that is being cancelled is on its way out: asking again starts a fresh one behind it.
            if active is not None and not active["cancel_requested"]:
                return dict(self.public(active), merged=True)
            if self.db.count_active_jobs() >= MAX_QUEUED:
                raise QueueFull()
            job_id = new_id(12)
            self.db.create_job(job_id, key, "spectrum", params.normalized())
            self._q.put(job_id)
            return self._with_queue(self.db.get_job(job_id))

    def cancel(self, job_id: str) -> dict | None:
        job = self.db.get_job(job_id)
        if job is None:
            return None
        if job["status"] not in TERMINAL:
            self.db.request_cancel(job_id)
            if job["status"] == "queued":
                # henüz başlamadıysa hemen sonlandır; işçi kuyruktan aldığında atlar
                self.db.update_job(job_id, status="cancelled", stage="cancelled")
        return self.public(self.db.get_job(job_id))

    def get(self, job_id: str) -> dict | None:
        job = self.db.get_job(job_id)
        return self._with_queue(job) if job else None

    def _with_queue(self, job: dict) -> dict:
        out = self.public(job)
        if job["status"] == "queued":
            out["ahead"] = self.db.count_active_before(job["id"])      # shown to the user: why it is waiting
        return out

    @staticmethod
    def public(job: dict) -> dict:
        return {
            "id": job["id"], "kind": job["kind"], "status": job["status"], "stage": job["stage"], "progress": round(float(job["progress"]), 3),
            "result_id": job.get("sequence_id") if job["kind"] == "spectrum" else None,
            "detail": job.get("detail"), "error": job.get("error"), "sequence_id": job.get("sequence_id"),
            "cancel_requested": job["cancel_requested"], "params": job["params"],
            "created_at": job["created_at"], "updated_at": job["updated_at"],
        }

    # ------------------------------------------------------------------ işçi
    def _loop(self) -> None:
        while not self._stopping:
            job_id = self._q.get()
            if job_id is None:
                return
            try:
                self._run(job_id)
            except Exception:  # işçi asla ölmemeli
                log.error("worker crash on %s\n%s", job_id, traceback.format_exc())
                try:
                    self.db.update_job(job_id, status="failed", stage="failed", error="internal_error")
                except Exception:
                    pass

    def _run(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if job is None or job["status"] in TERMINAL:
            return
        if job["cancel_requested"]:
            self.db.update_job(job_id, status="cancelled", stage="cancelled")
            return
        p = job["params"]
        if job["kind"] == "spectrum":
            self._run_spectrum(job_id, p)
            return
        params = SearchParams(p["ra_deg"], p["dec_deg"], p["fov_arcmin"], p["lam_um"], p["tol"], p["max_frames"],
                              p["mjd_min"], p["mjd_max"], p["target_id"])
        last = {"t": 0.0, "stage": None}

        def report(stage: str, progress: float, detail: dict | None = None) -> None:
            # Aşama değişimi her zaman yazılır (durum gerçek aşamayı göstermeli); aynı aşamadaki ilerleme seyreltilir.
            now = time.monotonic()
            if stage == "done":
                return
            if stage != last["stage"] or now - last["t"] >= 0.25:
                last["t"], last["stage"] = now, stage
                self.db.update_job(job_id, status=stage, stage=stage, progress=float(progress), detail=detail)

        try:
            self.db.update_job(job_id, status="searching", stage="searching", progress=0.01)
            res = self.pipeline.run(params, report, lambda: self.db.is_cancel_requested(job_id))
            self.db.update_job(job_id, status=res["status"], stage="done", progress=1.0, sequence_id=res["sequence_id"],
                               detail={"reused": res.get("reused", False), "reason": res.get("reason")})
        except Cancelled:
            self.db.update_job(job_id, status="cancelled", stage="cancelled")
        except InsufficientData as exc:
            self.db.update_job(job_id, status="insufficient_data", stage="done", progress=1.0,
                               detail=dict(exc.detail, reason=exc.reason))
        except TimeoutError:
            self.db.update_job(job_id, status="failed", stage="failed", error="timeout")
        except (ArchiveError, CutoutError) as exc:
            log.warning("archive error on %s: %s", job_id, exc)
            older = self.db.latest_sequence_for(job["request_key"])
            if older is not None and older["status"] == "ready":
                # The archive is down, but these frames were fetched before for the same request: open them and
                # say when they were fetched, rather than leave the visitor with nothing.
                self.db.update_job(job_id, status="done", stage="done", progress=1.0, sequence_id=older["id"],
                                   detail={"stale": True, "fetched_at": older["created_at"], "message": str(exc)[:300]})
            else:
                self.db.update_job(job_id, status="failed", stage="failed", error="archive_error", detail={"message": str(exc)[:300]})
        except Exception:
            log.error("job %s failed\n%s", job_id, traceback.format_exc())
            self.db.update_job(job_id, status="failed", stage="failed", error="internal_error")

    def _run_spectrum(self, job_id: str, p: dict) -> None:
        params = SpectrumParams(p["ra_deg"], p["dec_deg"], p["mjd_center"], p["window_days"], p["max_points"], p["target_id"],
                                p.get("lam_min_um"), p.get("lam_max_um"))
        last = {"t": 0.0, "stage": None}

        def report(stage: str, progress: float, detail: dict | None = None) -> None:
            now = time.monotonic()
            if stage != "done" and (stage != last["stage"] or now - last["t"] >= 0.25):
                last["t"], last["stage"] = now, stage
                self.db.update_job(job_id, status=stage, stage=stage, progress=float(progress), detail=detail)

        try:
            self.db.update_job(job_id, status="searching", stage="searching", progress=0.01)
            res = run_spectrum(self.pipeline, params, report, lambda: self.db.is_cancel_requested(job_id))
            self.db.update_job(job_id, status=res["status"], stage="done", progress=1.0, sequence_id=res["result_id"],
                               detail={"reused": res.get("reused", False)})
        except Cancelled:
            self.db.update_job(job_id, status="cancelled", stage="cancelled")
        except InsufficientData as exc:
            self.db.update_job(job_id, status="insufficient_data", stage="done", progress=1.0, detail=dict(exc.detail, reason=exc.reason))
        except (ArchiveError, CutoutError) as exc:
            self.db.update_job(job_id, status="failed", stage="failed", error="archive_error", detail={"message": str(exc)[:300]})
        except Exception:
            log.error("spectrum job %s failed\n%s", job_id, traceback.format_exc())
            self.db.update_job(job_id, status="failed", stage="failed", error="internal_error")
