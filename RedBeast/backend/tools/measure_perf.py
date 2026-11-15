"""Çalışan sunucuya karşı gerçek performans ölçümleri.

Kullanım:  python -m tools.measure_perf [--base http://127.0.0.1:8765] [--new-ra 83.8221 --new-dec -5.3911]

Ölçülenler (hepsi gerçek HTTP istekleriyle; tekrar sayıları çıktıda yazar):
- hazır hedefin açılışı (hedef listesi + dizi + tüm kare PNG'leri): süre ve aktarılan bayt
- önbellekten arama (POST /api/searches → anında done)
- yeni koordinatta arama + hazırlama (gerçek arşiv; N=1) ve bu sırada sunucu belleği (RSS)
- sınırlı eşzamanlı istek altında davranış
Çıktı: reports/performance.json ve reports/performance.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[2]


def server_process(port: int):
    for c in psutil.net_connections(kind="tcp"):
        if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN and c.pid:
            return psutil.Process(c.pid)
    return None


def stats(xs: list[float]) -> dict:
    return {"n": len(xs), "median": round(statistics.median(xs), 3), "min": round(min(xs), 3), "max": round(max(xs), 3)}


def open_sequence(client: httpx.Client, seq_id: str) -> tuple[float, int, int]:
    """Bir diziyi tarayıcının yaptığı gibi açar: JSON + tüm kare PNG'leri. Döner: (süre, bayt, kare sayısı)."""
    t0 = time.perf_counter()
    r = client.get(f"/api/sequences/{seq_id}")
    r.raise_for_status()
    n = len(r.content)
    frames = r.json()["frames"]
    for f in frames:
        img = client.get(f["image_url"])
        img.raise_for_status()
        n += len(img.content)
    return time.perf_counter() - t0, n, len(frames)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--new-ra", default="83.8221")     # Orion Bulutsusu yakınında, hazır listede olmayan bir konum
    ap.add_argument("--new-dec", default="-5.3911")
    ap.add_argument("--skip-new", action="store_true")
    ap.add_argument("--pid", type=int, help="Known owned server PID; avoids system-wide process inspection")
    a = ap.parse_args()
    port = int(a.base.rsplit(":", 1)[1].split("/")[0])
    if a.pid:
        proc = psutil.Process(a.pid)
    else:
        try:
            proc = server_process(port)
        except psutil.AccessDenied:
            proc = None
    out = {"measured_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "base": a.base,
           "environment": {"os": platform.platform(), "python": platform.python_version(), "cpu_count": psutil.cpu_count(),
                           "ram_gb": round(psutil.virtual_memory().total / 2 ** 30, 1), "server": "uvicorn, 1 process, 1 worker thread",
                           "network": "sunucu ve istemci aynı makinede (localhost); arşiv erişimi ev/ofis internet bağlantısı üzerinden"}}
    with httpx.Client(base_url=a.base, timeout=600) as c:
        health = c.get("/api/health").json()
        out["pipeline_version"] = health["pipeline_version"]
        targets = c.get("/api/targets").json()["targets"]
        ready = {t["id"]: t["ready_sequence_id"] for t in targets if t["ready_sequence_id"]}

        # 1) hazır hedef açılışı
        per = {}
        for tid, sid in ready.items():
            times, nbytes, nfr = [], 0, 0
            for _ in range(5):
                t0 = time.perf_counter()
                c.get("/api/targets").raise_for_status()
                dt_s, nbytes, nfr = open_sequence(c, sid)
                times.append(time.perf_counter() - t0)
            per[tid] = {"sequence_id": sid, "frames": nfr, "bytes": nbytes, "seconds": stats(times)}
        out["preset_open"] = per

        # 2) önbellekten arama
        times = []
        for tid in list(ready)[:5]:
            t0 = time.perf_counter()
            r = c.post("/api/searches", json={"target_id": tid})
            r.raise_for_status()
            assert r.json()["job"]["status"] in ("done", "insufficient_data"), r.json()
            times.append(time.perf_counter() - t0)
        out["cached_search"] = {"seconds": stats(times), "note": "POST /api/searches → iş anında 'done' (dizi önbellekte)"}

        # 3) sınırlı eşzamanlılık: 24 eşzamanlı okuma isteği (8 iş parçacığı)
        sid = next(iter(ready.values()))
        seq = c.get(f"/api/sequences/{sid}").json()
        urls = [f["image_url"] for f in seq["frames"]] * 4
        urls = (urls + [f"/api/sequences/{sid}", "/api/targets", "/api/health"] * 4)[:24]

        def one(u):
            t0 = time.perf_counter()
            r = c.get(u)
            return r.status_code, time.perf_counter() - t0

        t0 = time.perf_counter()
        with ThreadPoolExecutor(8) as pool:
            res = list(pool.map(one, urls))
        out["concurrent_reads"] = {"requests": len(urls), "threads": 8, "all_ok": all(s == 200 for s, _ in res),
                                   "wall_s": round(time.perf_counter() - t0, 3), "per_request_s": stats([d for _, d in res])}

        # 4) aynı isteğin eşzamanlı gönderimi: tek iş (birleştirme) ve hız sınırı
        if not a.skip_new:
            rss, stop = [], threading.Event()

            def sample():
                while not stop.is_set():
                    if proc is not None:
                        try:
                            rss.append(proc.memory_info().rss)
                        except psutil.Error:
                            pass
                    stop.wait(0.5)

            idle = proc.memory_info().rss if proc else None
            th = threading.Thread(target=sample, daemon=True)
            th.start()
            body = {"ra": a.new_ra, "dec": a.new_dec, "ra_unit": "deg", "fov_arcmin": 6, "max_frames": 4, "refresh": True}
            t0 = time.perf_counter()
            with ThreadPoolExecutor(4) as pool:
                jobs = list(pool.map(lambda _: c.post("/api/searches", json=body).json()["job"], range(4)))
            ids = {j["id"] for j in jobs}
            job = jobs[0]
            stage_t = {}
            while job["status"] not in ("done", "insufficient_data", "failed", "cancelled"):
                stage_t.setdefault(job["status"], round(time.perf_counter() - t0, 1))
                time.sleep(0.5)
                job = c.get(f"/api/jobs/{job['id']}").json()["job"]
            total = time.perf_counter() - t0
            stop.set()
            th.join()
            rec = {"position": {"ra": a.new_ra, "dec": a.new_dec}, "status": job["status"], "total_s": round(total, 1), "stage_first_seen_s": stage_t,
                   "simultaneous_submissions": 4, "distinct_jobs_created": len(ids), "n": 1}
            if job.get("sequence_id"):
                m = c.get(f"/api/sequences/{job['sequence_id']}").json()["meta"]
                rec.update(sequence_id=job["sequence_id"], n_frames=m["n_frames"], n_visits=m["n_visits"], timings=m["timings"],
                           archive_rows=m["archive"]["n_rows"], archive_elapsed_s=m["archive"]["elapsed_s"])
                dt_s, nbytes, nfr = open_sequence(c, job["sequence_id"])
                rec["browser_transfer_bytes"] = nbytes
            if rss:
                rec["server_rss_mb"] = {"idle": round(idle / 2 ** 20, 1), "peak": round(max(rss) / 2 ** 20, 1), "samples": len(rss), "interval_s": 0.5}
            out["new_coordinate"] = rec

        # 5) hız sınırı: bir dakikada 12'den fazla arama isteği 429 döner
        codes = [c.post("/api/searches", json={"ra": "abc", "dec": "0"}).status_code for _ in range(14)]
        out["rate_limit"] = {"limit_per_minute": 12, "codes": codes, "got_429": 429 in codes}

    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "performance.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
