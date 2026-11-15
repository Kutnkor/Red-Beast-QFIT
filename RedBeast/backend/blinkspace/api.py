"""BlinkSpace HTTP API (FastAPI).

Uzun işlemler istek ömrüne bağlı değildir: `POST /api/searches` bir iş döndürür, istemci
`GET /api/jobs/{id}` ile durumu izler. Üyelik yoktur; paylaşılan gözlemler düzenleme anahtarıyla korunur.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.datastructures import MutableHeaders

from .analysis import Analysis, AnalysisError
from .archive import ArchiveError
from .config import PIPELINE_VERSION, Settings, load_settings
from .coords import CoordinateError, format_dec_dms, format_ra_hms, parse_position
from .db import Database
from .jobs import JobManager, QueueFull
from .pipeline import Pipeline, SearchParams, new_id
from .spectrum import SpectrumParams, load_spectrum
from .targets import RESOURCES, load_targets, load_targets_doc, public_target
from .tracks import load_track
from .wavelength import WaveModel

log = logging.getLogger("blinkspace.api")
CLASSIFICATIONS = ("possible_motion", "possible_brightness_change", "possible_artifact", "unsure")
_FILE_OK = re.compile(r"^(frame_\d{2}(_mask)?|diff_\d{2}_\d{2}|stack|track_stack)\.png$")
_ID_OK = re.compile(r"^[a-z0-9]{6,24}$")
MJD_EPOCH_UNIX = 40587.0


class ResponseHeadersMiddleware:
    """Pure ASGI: preserve streaming/file events and disconnect semantics.

    BaseHTTPMiddleware's wrapped receive stream can prematurely cancel modern
    Starlette FileResponse on an ASGI 2.3 server. Header edits need no wrapper
    response or buffering, so perform them only at http.response.start.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                                   "script-src 'self'; connect-src 'self'; frame-ancestors *; base-uri 'self'")
                if scope["path"].startswith("/api/") and "Cache-Control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, with_headers)


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str = "", **extra):
        super().__init__(status_code=status, detail={"code": code, "message": message or code, **extra})


# ---------------------------------------------------------------------------- şemalar
class SearchIn(BaseModel):
    target_id: str | None = Field(default=None, max_length=40)
    ra: str | float | None = None
    dec: str | float | None = None
    ra_unit: Literal["auto", "deg", "hour"] = "auto"
    fov_arcmin: float | None = None
    lam_um: float | None = None
    tol: float = 0.5
    max_frames: int | None = None
    date_from: str | None = Field(default=None, max_length=32)
    date_to: str | None = Field(default=None, max_length=32)
    refresh: bool = False

    @field_validator("fov_arcmin", "lam_um", "tol")
    @classmethod
    def _finite(cls, v):
        if v is not None and not math.isfinite(v):
            raise ValueError("sonlu bir sayı olmalı")
        return v


class SpectrumIn(BaseModel):
    target_id: str | None = Field(default=None, max_length=40)
    ra: str | float | None = None
    dec: str | float | None = None
    ra_unit: Literal["auto", "deg", "hour"] = "auto"
    date: str | None = Field(default=None, max_length=32)       # pencere merkezi; boşsa en yoğun pencere
    window_days: float = Field(default=14.0, ge=1.0, le=60.0)
    max_points: int = Field(default=24, ge=3, le=40)
    lam_min_um: float | None = Field(default=None, ge=0.7, le=5.1)
    lam_max_um: float | None = Field(default=None, ge=0.7, le=5.1)


class MarkIn(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    kind: Literal["point", "region"] = "point"
    classification: Literal["possible_motion", "possible_brightness_change", "possible_artifact", "unsure"]
    ra_deg: float = Field(ge=0.0, lt=360.0)
    dec_deg: float = Field(ge=-90.0, le=90.0)
    radius_arcsec: float | None = Field(default=None, gt=0.0, le=900.0)
    frame_index: int = Field(ge=0, le=99)
    note: str = Field(default="", max_length=500)
    track_id: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")


class ObservationUpdate(BaseModel):
    title: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=2000)
    marks: list[MarkIn] = Field(default_factory=list, max_length=200)
    view: dict = Field(default_factory=dict)

    @field_validator("view")
    @classmethod
    def _small_view(cls, v):
        if len(json.dumps(v)) > 2000:
            raise ValueError("görünüm durumu çok büyük")
        return v


class ObservationIn(ObservationUpdate):
    sequence_id: str = Field(pattern=r"^[a-z0-9]{6,24}$")


# ---------------------------------------------------------------------------- yardımcılar
def parse_date(text: str | None) -> float | None:
    """ISO tarih (YYYY-MM-DD[THH:MM[:SS]]) veya MJD sayısı -> MJD (UTC)."""
    if text is None or not str(text).strip():
        return None
    s = str(text).strip()
    try:
        v = float(s)
        if 50000.0 <= v <= 90000.0:
            return v
        raise ApiError(422, "bad_date", "MJD 50000–90000 aralığında olmalı")
    except ValueError:
        pass
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?Z?$", s)
    if not m:
        raise ApiError(422, "bad_date", "Tarih YYYY-AA-GG biçiminde olmalı")
    import calendar
    y, mo, d = int(m[1]), int(m[2]), int(m[3])
    hh, mm, ss = int(m[4] or 0), int(m[5] or 0), int(m[6] or 0)
    try:
        unix = calendar.timegm((y, mo, d, hh, mm, ss))
        if time.gmtime(unix)[:3] != (y, mo, d):
            raise ValueError
    except (ValueError, OverflowError):
        raise ApiError(422, "bad_date", "Geçersiz tarih")
    return MJD_EPOCH_UNIX + unix / 86400.0


class RateLimiter:
    """Basit bellek içi kayan pencere sınırlayıcı (IP başına)."""

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window = limit, window_s
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 5000:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
            return True


def sequence_public(seq: dict) -> dict:
    base = f"/api/sequences/{seq['id']}/files/"
    frames = []
    for f in seq["frames"]:
        g = {k: v for k, v in f.items() if k not in ("png", "mask_png", "npz")}
        g["image_url"] = base + f["png"]
        g["mask_url"] = base + f["mask_png"]
        frames.append(g)
    return {"id": seq["id"], "status": seq["status"], "params": seq["params"], "meta": seq["meta"], "frames": frames,
            "created_at": seq["created_at"]}


def load_tutorials() -> list[dict]:
    p = RESOURCES / "tutorials.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))["tutorials"]


# ---------------------------------------------------------------------------- uygulama
def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None, start_workers: bool = True) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    targets = load_targets()
    pipe = pipeline or Pipeline(settings, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    interrupted = db.interrupt_unfinished_jobs()
    if interrupted:
        log.warning("%d yarım iş 'interrupted_by_restart' olarak işaretlendi", interrupted)
    db.replace_tutorials(load_tutorials())
    jobs = JobManager(pipe, db, settings, workers=1, autostart=start_workers)
    analysis = Analysis(settings, db, pipe)
    search_limiter = RateLimiter(12, 60.0)
    write_limiter = RateLimiter(30, 60.0)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        jobs.stop()

    app = FastAPI(title="BlinkSpace API", version=PIPELINE_VERSION, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.settings, app.state.db, app.state.jobs, app.state.pipeline = settings, db, jobs, pipe
    from .assistant import build_assistant_router
    app.include_router(build_assistant_router(RateLimiter))

    @app.exception_handler(HTTPException)
    async def _http_exc(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content={"error": detail}, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # Girdi değerleri yanıta geri yazılmaz (NaN gibi JSON'a çevrilemeyen değerler ve yansıtma riski).
        fields = [{"loc": [str(x) for x in e.get("loc", ())], "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))}
                  for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Geçersiz istek", "fields": fields}})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Beklenmeyen sunucu hatası"}})

    app.add_middleware(ResponseHeadersMiddleware)

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def get_seq(seq_id: str) -> dict:
        if not _ID_OK.match(seq_id):
            raise ApiError(404, "sequence_not_found")
        seq = db.get_sequence(seq_id)
        if seq is None:
            raise ApiError(404, "sequence_not_found")
        return seq

    # ---- genel -----------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": "BlinkSpace", "pipeline_version": PIPELINE_VERSION, "active_jobs": db.count_active_jobs(),
                "limits": {"fov_arcmin": [settings.min_fov_arcmin, settings.max_fov_arcmin], "max_frames": settings.max_frames,
                           "default_fov_arcmin": settings.default_fov_arcmin, "default_frames": settings.default_frames},
                "classifications": list(CLASSIFICATIONS)}

    def science_resource(name: str, media_type: str):
        path = RESOURCES / name
        if not path.is_file():
            raise ApiError(503, "science_resource_unavailable", "Scientific catalogue has not been prepared")
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/api/motion")
    def motion_catalogue():
        return science_resource("motion_catalogue.json", "application/json")

    @app.get("/api/models")
    def stellar_profiles():
        return science_resource("stellar_profiles.json", "application/json")

    @app.get("/api/sky/bright.bin")
    def bright_sky_binary():
        return science_resource("bright_sky.bin", "application/octet-stream")

    @app.get("/api/sky/bright.json")
    def bright_sky_metadata():
        return science_resource("bright_sky.json", "application/json")

    @app.get("/api/targets")
    def list_targets():
        ready = db.get_meta("preset_sequences", {})
        out = []
        for t in targets.values():
            item = public_target(t)
            item["preferred_lam_um"] = t.get("preferred_lam_um")
            sid = ready.get(t["id"])
            item["ready_sequence_id"] = sid if sid and db.get_sequence(sid) else None
            out.append(item)
        return {"source": load_targets_doc()["source"], "generated_at": load_targets_doc()["generated_at"], "targets": out}

    # ---- arama ve işler --------------------------------------------------------------
    @app.post("/api/searches", status_code=202)
    def start_search(body: SearchIn, request: Request):
        if not search_limiter.allow(client_ip(request)):
            raise ApiError(429, "rate_limited", "Çok fazla arama isteği; biraz sonra yeniden deneyin")
        notes: list[str] = []
        lam = body.lam_um
        if body.target_id:
            t = targets.get(body.target_id)
            if t is None:
                raise ApiError(404, "target_not_found")
            ra, dec = t["search"]["ra_deg"], t["search"]["dec_deg"]
            if lam is None:
                lam = t.get("preferred_lam_um")
            fov = body.fov_arcmin if body.fov_arcmin is not None else t["search"]["fov_arcmin"]
        else:
            if body.ra is None or body.dec is None:
                raise ApiError(422, "missing_coordinates", "RA ve Dec gerekli")
            try:
                pos = parse_position(body.ra, body.dec, body.ra_unit)
            except CoordinateError as exc:
                raise ApiError(422, "bad_coordinates", str(exc), reason=exc.code)
            ra, dec, notes = pos.ra_deg, pos.dec_deg, list(pos.notes)
            fov = body.fov_arcmin if body.fov_arcmin is not None else settings.default_fov_arcmin
        if not (settings.min_fov_arcmin <= fov <= settings.max_fov_arcmin):
            raise ApiError(422, "bad_fov", f"Alan {settings.min_fov_arcmin}–{settings.max_fov_arcmin} yay dakikası olmalı")
        frames = body.max_frames if body.max_frames is not None else settings.default_frames
        if not (2 <= frames <= settings.max_frames):
            raise ApiError(422, "bad_max_frames", f"Kare sayısı 2–{settings.max_frames} olmalı")
        if not (0.05 <= body.tol <= 1.0):
            raise ApiError(422, "bad_tolerance", "Tolerans 0.05–1.0 olmalı")
        if lam is not None and not (0.7 <= lam <= 5.1):
            raise ApiError(422, "bad_wavelength", "Dalga boyu 0.7–5.1 µm olmalı")
        mjd_min, mjd_max = parse_date(body.date_from), parse_date(body.date_to)
        if mjd_min is not None and mjd_max is not None and mjd_min >= mjd_max:
            raise ApiError(422, "bad_date_range", "Başlangıç tarihi bitişten önce olmalı")
        params = SearchParams(ra, dec, fov, lam, body.tol, frames, mjd_min, mjd_max, body.target_id)
        try:
            job = jobs.submit(params, force_refresh=body.refresh)
        except QueueFull:
            raise ApiError(503, "queue_full", "Sunucu meşgul; biraz sonra yeniden deneyin")
        db.add_search(new_id(12), params.request_key(), params.normalized(), job["id"])
        return {"job": job, "position": {"ra_deg": ra, "dec_deg": dec, "frame": "ICRS", "ra_hms": format_ra_hms(ra),
                                         "dec_dms": format_dec_dms(dec), "notes": notes}}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        job = jobs.get(job_id) if _ID_OK.match(job_id) else None
        if job is None:
            raise ApiError(404, "job_not_found")
        return {"job": job}

    @app.post("/api/jobs/{job_id}/cancel")
    def job_cancel(job_id: str):
        job = jobs.cancel(job_id) if _ID_OK.match(job_id) else None
        if job is None:
            raise ApiError(404, "job_not_found")
        return {"job": job}

    # ---- spektrum ---------------------------------------------------------------------
    @app.post("/api/spectra", status_code=202)
    def start_spectrum(body: SpectrumIn, request: Request):
        if not search_limiter.allow(client_ip(request)):
            raise ApiError(429, "rate_limited", "Çok fazla istek; biraz sonra yeniden deneyin")
        if body.target_id:
            t = targets.get(body.target_id)
            if t is None:
                raise ApiError(404, "target_not_found")
            ra, dec = t["search"]["ra_deg"], t["search"]["dec_deg"]
        else:
            if body.ra is None or body.dec is None:
                raise ApiError(422, "missing_coordinates", "RA ve Dec gerekli")
            try:
                pos = parse_position(body.ra, body.dec, body.ra_unit)
            except CoordinateError as exc:
                raise ApiError(422, "bad_coordinates", str(exc), reason=exc.code)
            ra, dec = pos.ra_deg, pos.dec_deg
        if body.lam_min_um is not None and body.lam_max_um is not None and body.lam_min_um >= body.lam_max_um:
            raise ApiError(422, "bad_wavelength", "Dalga boyu aralığı geçersiz")
        params = SpectrumParams(ra, dec, parse_date(body.date), body.window_days, body.max_points, body.target_id,
                                body.lam_min_um, body.lam_max_um)
        try:
            job = jobs.submit_spectrum(params)
        except QueueFull:
            raise ApiError(503, "queue_full", "Sunucu meşgul; biraz sonra yeniden deneyin")
        return {"job": job}

    @app.get("/api/spectra/{result_id}")
    def get_spectrum(result_id: str):
        res = load_spectrum(settings, result_id) if re.match(r"^[a-f0-9]{32}$", result_id) else None
        if res is None:
            raise ApiError(404, "spectrum_not_found")
        return res

    # ---- diziler ---------------------------------------------------------------------
    @app.get("/api/sequences/{seq_id}")
    def sequence(seq_id: str):
        return sequence_public(get_seq(seq_id))

    @app.get("/api/sequences/{seq_id}/files/{name}")
    def sequence_file(seq_id: str, name: str):
        seq = get_seq(seq_id)
        if not _FILE_OK.match(name):
            raise ApiError(404, "file_not_found")
        path = settings.processed_dir / seq["id"] / name
        if not path.is_file():
            raise ApiError(404, "file_not_found")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/api/sequences/{seq_id}/provenance")
    def provenance(seq_id: str):
        seq = get_seq(seq_id)
        m = seq["meta"]
        return {
            "sequence_id": seq["id"], "pipeline_version": m["pipeline_version"], "created_at": m["created_at"],
            "archive": m["archive"], "selection": m["selection"], "wavelength": {k: m["wavelength"][k] for k in ("lam_ref_um", "bw_ref_um", "tol", "mode")},
            "alignment": m["alignment"], "display": m["display"], "data_fingerprint": m["data_fingerprint"],
            "frames": [{k: f[k] for k in ("index", "obs_id", "detector", "collection", "release", "l2_tag", "pipeline_version", "timesys",
                                           "mjd_beg", "mjd_avg", "mjd_end", "date_avg", "exposure_s", "lam_um", "bw_um", "dlam_over_bw",
                                           "source_url", "archive_file_url", "archive_checksum", "raw_sha256", "raw_size", "quality",
                                           "background", "coverage_frac", "invalid_frac", "suspect_frac", "comparable_frac", "cutout_wcs")}
                       for f in seq["frames"]],
            "citation": "SPHEREx Team (2025), SPHEREx Quick Release Spectral Images, IRSA, doi:10.26131/IRSA629",
        }

    def analysis_call(fn, *args):
        try:
            return fn(*args)
        except AnalysisError as exc:
            raise ApiError(422, exc.code, str(exc))
        except ArchiveError as exc:
            raise ApiError(502, "archive_error", str(exc)[:200])

    @app.get("/api/assistant/comparison/{seq_id}")
    def assistant_comparison(seq_id: str, a: int | None = None, b: int | None = None):
        from .qfit_comparison import compare_observations

        return analysis_call(compare_observations, analysis, get_seq(seq_id), a, b)

    @app.get("/api/sequences/{seq_id}/diff")
    def diff(seq_id: str, a: int, b: int):
        seq = get_seq(seq_id)
        out = analysis_call(analysis.diff, seq, a, b)
        out["image_url"] = f"/api/sequences/{seq['id']}/files/{out['file']}"
        return out

    @app.get("/api/sequences/{seq_id}/stack")
    def stack(seq_id: str):
        seq = get_seq(seq_id)
        out = analysis_call(analysis.stack, seq)
        out["image_url"] = f"/api/sequences/{seq['id']}/files/{out['file']}"
        return out

    @app.get("/api/sequences/{seq_id}/track")
    def target_track(seq_id: str):
        return load_track(settings.processed_dir, get_seq(seq_id))

    @app.get("/api/sequences/{seq_id}/track_stack")
    def target_track_stack(seq_id: str):
        seq = get_seq(seq_id)
        out = analysis_call(analysis.track_stack, seq)
        out["image_url"] = f"/api/sequences/{seq['id']}/files/{out['file']}"
        return out

    @app.get("/api/sequences/{seq_id}/lightcurve")
    def lightcurve(seq_id: str, ra: float | None = None, dec: float | None = None, follow_target: bool = False):
        seq = get_seq(seq_id)
        if not follow_target:
            if ra is None or dec is None or not (math.isfinite(ra) and math.isfinite(dec)) or not (0 <= ra < 360 and -90 <= dec <= 90):
                raise ApiError(422, "bad_coordinates", "ra ve dec gerekli")
        return analysis_call(analysis.lightcurve, seq, ra, dec, follow_target)

    @app.get("/api/sequences/{seq_id}/overlay")
    def overlay(seq_id: str, catalog: Literal["gaia", "allwise"]):
        return analysis_call(analysis.overlay, get_seq(seq_id), catalog)

    @app.get("/api/sequences/{seq_id}/candidates")
    def candidates(seq_id: str, a: int, b: int):
        return analysis_call(analysis.candidates, get_seq(seq_id), a, b)

    # ---- paylaşılan gözlemler --------------------------------------------------------
    def clean_marks(seq: dict, marks: list[MarkIn]) -> list[dict]:
        out = []
        n = len(seq["frames"])
        for m in marks:
            if m.frame_index >= n:
                raise ApiError(422, "bad_mark", "İşaret var olmayan bir kareye bağlı")
            if m.kind == "region" and m.radius_arcsec is None:
                raise ApiError(422, "bad_mark", "Bölge işareti için yarıçap gerekli")
            f = seq["frames"][m.frame_index]
            d = m.model_dump()
            # işaret; gökyüzü koordinatı + ilgili kare + gözlem zamanı ile saklanır (sunucu kareden doldurur)
            d.update(obs_id=f["obs_id"], detector=f["detector"], mjd=f["mjd_avg"], date=f["date_avg"], lam_um=f["lam_um"],
                     status="unverified")
            out.append(d)
        if len({m["id"] for m in out}) != len(out):
            raise ApiError(422, "bad_mark", "İşaret kimlikleri benzersiz olmalı")
        return out

    def shared_public(rec: dict, seq: dict) -> dict:
        return {"id": rec["id"], "sequence_id": rec["sequence_id"], "title": rec["title"], "note": rec["note"],
                "marks": rec["marks"], "view": rec["view"], "app_version": rec["app_version"],
                "created_at": rec["created_at"], "updated_at": rec["updated_at"],
                "status": "unverified_user_observation", "sequence": sequence_public(seq)}

    @app.post("/api/observations", status_code=201)
    def create_observation(body: ObservationIn, request: Request):
        if not write_limiter.allow(client_ip(request)):
            raise ApiError(429, "rate_limited")
        seq = get_seq(body.sequence_id)
        token = secrets.token_urlsafe(24)
        now = time.time()
        rec = {"id": new_id(10), "sequence_id": seq["id"], "title": body.title.strip(), "note": body.note.strip(),
               "marks": clean_marks(seq, body.marks), "view": body.view,
               "edit_token_hash": hashlib.sha256(token.encode()).hexdigest(), "app_version": PIPELINE_VERSION,
               "created_at": now, "updated_at": now}
        db.put_shared(rec)
        return {"observation": shared_public(rec, seq), "edit_token": token, "share_path": f"/o/{rec['id']}"}

    def owned(obs_id: str, token: str | None) -> dict:
        rec = db.get_shared(obs_id) if _ID_OK.match(obs_id) else None
        if rec is None:
            raise ApiError(404, "observation_not_found")
        if not token or not secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(), rec["edit_token_hash"]):
            raise ApiError(403, "not_owner", "Bu gözlemi düzenleme yetkiniz yok")
        return rec

    @app.get("/api/observations/{obs_id}")
    def get_observation(obs_id: str):
        rec = db.get_shared(obs_id) if _ID_OK.match(obs_id) else None
        if rec is None:
            raise ApiError(404, "observation_not_found")
        return {"observation": shared_public(rec, get_seq(rec["sequence_id"]))}

    @app.put("/api/observations/{obs_id}")
    def update_observation(obs_id: str, body: ObservationUpdate, request: Request, x_edit_token: str | None = Header(default=None)):
        if not write_limiter.allow(client_ip(request)):
            raise ApiError(429, "rate_limited")
        rec = owned(obs_id, x_edit_token)
        seq = get_seq(rec["sequence_id"])
        db.update_shared(obs_id, body.title.strip(), body.note.strip(), clean_marks(seq, body.marks), body.view)
        return {"observation": shared_public(db.get_shared(obs_id), seq)}

    @app.delete("/api/observations/{obs_id}", status_code=204)
    def delete_observation(obs_id: str, x_edit_token: str | None = Header(default=None)):
        owned(obs_id, x_edit_token)
        db.delete_shared(obs_id)
        return None

    # ---- öğretici görevler -----------------------------------------------------------
    @app.get("/api/tutorials")
    def tutorials():
        return {"tutorials": db.list_tutorials()}

    # ---- arayüz (derlenmiş statik dosyalar) -------------------------------------------
    dist = settings.frontend_dist
    index = dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise ApiError(404, "not_found")
        if index.is_file():
            cand = (dist / full_path).resolve()
            if full_path and cand.is_file() and dist in cand.parents:
                cache = "public, max-age=31536000, immutable" if "/assets/" in f"/{full_path}" else "no-cache"
                return FileResponse(cand, headers={"Cache-Control": cache})
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"app": "BlinkSpace API", "note": "Arayüz derlenmemiş. `npm run build` (frontend/) çalıştırın.", "docs": "/api/docs"})

    return app


def app_factory() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return create_app()
