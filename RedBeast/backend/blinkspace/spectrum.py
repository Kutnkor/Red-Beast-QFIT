"""Anlık spektrum: bir gökyüzü konumunda, belirli bir zaman penceresindeki SPHEREx pozlamalarından
dalga boyuna karşı açıklık akısı.

Kurallar:
- Her nokta kendi ölçüm zamanını, dalga boyunu, bant genişliğini, kalite bayraklarını ve belirsizliğini taşır.
- Noktalar **eşzamanlı değildir**: SPHEREx bir kaynağın tayfını günler–haftalar içinde tarar. Pencere ve her
  noktanın tarihi açıkça verilir; değişen bir kaynakta bu bir "anlık" tayf olarak sunulmaz.
- Ölçüm ham (yeniden örneklenmemiş) piksellerden yapılır; geçersiz pikselli ölçümler "yok" kalır.
- Hızlı hareket eden hazır hedeflerde konum, her pozlamanın tarihine yalnızca özdevinimle ilerletilir.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from . import catalogs, selection
from .config import PIPELINE_VERSION
from .cutouts import CutoutError, cutout_url
from .photometry import aperture_photometry
from .spx import SpxFormatError, read_spx

SPECTRUM_CUTOUT_DEG = 0.05      # ~29 piksel: açıklık + arka plan halkası için yeterli
SPECTRUM_MIN_EDGE_PX = 20.0


@dataclass(frozen=True)
class SpectrumParams:
    ra_deg: float
    dec_deg: float
    mjd_center: float | None = None   # None: en çok pozlama içeren pencere
    window_days: float = 14.0
    max_points: int = 24
    target_id: str | None = None
    lam_min_um: float | None = None   # isteğe bağlı dalga boyu aralığı (ör. doymamış bölge)
    lam_max_um: float | None = None

    def normalized(self) -> dict:
        return {"ra_deg": round(self.ra_deg % 360.0, 5), "dec_deg": round(self.dec_deg, 5),
                "mjd_center": None if self.mjd_center is None else round(self.mjd_center, 2),
                "window_days": round(self.window_days, 2), "max_points": int(self.max_points), "target_id": self.target_id,
                "lam_min_um": None if self.lam_min_um is None else round(self.lam_min_um, 4),
                "lam_max_um": None if self.lam_max_um is None else round(self.lam_max_um, 4)}

    def request_key(self) -> str:
        doc = {"kind": "spectrum", "params": self.normalized(), "pipeline": PIPELINE_VERSION}
        return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:32]


def choose_window(cands, mjd_center: float | None, window_days: float) -> tuple[float, float]:
    """Pencere sınırları. Merkez verilmezse en çok aday içeren pencere seçilir."""
    if mjd_center is not None:
        return mjd_center - window_days / 2.0, mjd_center + window_days / 2.0
    times = sorted(c.obs.mjd_start for c in cands)
    best, best_n = times[0], 0
    j = 0
    for i, t in enumerate(times):
        while j < len(times) and times[j] <= t + window_days:
            j += 1
        if j - i > best_n:
            best, best_n = t, j - i
    return best - 1e-6, best + window_days


def pick_spread(cands, max_points: int):
    """Dalga boyu kapsamını koruyarak en çok `max_points` aday (dalga boyuna göre eşit aralıklı)."""
    ordered = sorted(cands, key=lambda c: c.lam_um)
    if len(ordered) <= max_points:
        return ordered
    idx = sorted({round(i * (len(ordered) - 1) / (max_points - 1)) for i in range(max_points)})
    return [ordered[i] for i in idx]


def run_spectrum(pipe, params: SpectrumParams, report=None, cancelled=None) -> dict:
    from .pipeline import Cancelled, InsufficientData, mjd_to_iso
    report = report or (lambda stage, progress, detail=None: None)
    cancelled = cancelled or (lambda: False)
    s = pipe.settings
    out_dir = s.processed_dir / "spectra"
    out_dir.mkdir(parents=True, exist_ok=True)
    key = params.request_key()
    path = out_dir / f"{key}.json"
    if is_fresh(s, key):
        report("done", 1.0, {"reused": True})
        return {"status": "done", "result_id": key, "reused": True}
    client = pipe._client_factory()
    try:
        report("searching", 0.02, None)
        from .archive import interruptible

        def check() -> None:
            if cancelled():
                raise Cancelled()

        with interruptible(check, lambda info: report("searching", 0.02, {"archive_wait": info})):
            kept, dropped, tap_meta = pipe.observations(params.ra_deg, params.dec_deg, client)
        if not kept:
            raise InsufficientData("no_coverage", {})
        cands, _ = selection.build_candidates(kept, params.ra_deg, params.dec_deg, pipe.model, SPECTRUM_MIN_EDGE_PX)
        cands = [c for c in cands if (params.lam_min_um is None or c.lam_um >= params.lam_min_um)
                 and (params.lam_max_um is None or c.lam_um <= params.lam_max_um)]
        if not cands:
            raise InsufficientData("no_usable_frames", {})
        t0, t1 = choose_window(cands, params.mjd_center, params.window_days)
        inside = [c for c in cands if t0 <= c.obs.mjd_start <= t1]
        if len(inside) < 3:
            raise InsufficientData("too_few_exposures_in_window", {"n": len(inside), "mjd_window": [t0, t1]})
        chosen = pick_spread(inside, params.max_points)
        if cancelled():
            raise Cancelled()
        target = pipe.targets.get(params.target_id or "")
        report("downloading", 0.1, {"n_frames": len(chosen), "n_done": 0})
        urls = [cutout_url(s.irsa_base, c.obs.uri, params.ra_deg, params.dec_deg, SPECTRUM_CUTOUT_DEG) for c in chosen]
        raws = {}
        with ThreadPoolExecutor(max_workers=max(1, s.download_concurrency)) as pool:
            futs = {pool.submit(pipe.store.get, u, client, s.http_timeout_s, s.max_retries): i for i, u in enumerate(urls)}
            for n_done, fut in enumerate(as_completed(futs), start=1):
                try:
                    raws[futs[fut]] = fut.result()
                except CutoutError:
                    pass
                report("downloading", 0.1 + 0.75 * n_done / len(urls), {"n_frames": len(urls), "n_done": n_done})
                if cancelled():
                    for f in futs:
                        f.cancel()
                    raise Cancelled()
        report("preparing", 0.88, None)
        points = []
        for i, c in enumerate(chosen):
            raw = raws.get(i)
            o = c.obs
            base = {"obs_id": o.obs_id, "detector": o.detector, "release": o.release, "l2_tag": o.l2_tag, "source_url": urls[i]}
            if raw is None:
                points.append(dict(base, valid=False, reason="download_failed", mjd=o.mjd_mid, date=mjd_to_iso(o.mjd_mid)))
                continue
            try:
                frame = read_spx(raw.path)
            except (SpxFormatError, OSError, ValueError):
                points.append(dict(base, valid=False, reason="unreadable_fits", mjd=o.mjd_mid, date=mjd_to_iso(o.mjd_mid)))
                continue
            ra, dec = params.ra_deg, params.dec_deg
            if target:
                ra, dec = catalogs.propagate(target["ra_deg"], target["dec_deg"], target.get("pmra_masyr"), target.get("pmdec_masyr"),
                                             target.get("epoch_jyear", 2000.0), catalogs.mjd_to_jyear(frame.mjd_avg))
            ph = aperture_photometry(frame, ra, dec)
            points.append(dict(base, mjd=frame.mjd_avg, date=mjd_to_iso(frame.mjd_avg), timesys=frame.timesys, ra=round(ra, 6), dec=round(dec, 6),
                               pipeline_version=frame.pipeline_version, raw_sha256=raw.sha256,
                               valid=ph["valid"], reliable=bool(ph.get("reliable")), reason=ph["reason"], saturated=ph["saturated"],
                               lam_um=ph["lam_um"], bw_um=ph["bw_um"], flux_mjy=ph["flux_mjy"], err_mjy=ph["err_mjy"], flags=ph["flags"]))
        points.sort(key=lambda p: (p.get("lam_um") or 99.0))
        good = [p for p in points if p["valid"] and p.get("reliable")]
        mjds = [p["mjd"] for p in points]
        result = {
            "id": key, "kind": "spectrum", "pipeline_version": PIPELINE_VERSION, "created_at": time.time(),
            "params": params.normalized(), "target_id": params.target_id,
            "position_mode": "follows_predicted_target" if target else "fixed_sky_position",
            "mjd_window": [round(t0, 4), round(t1, 4)], "date_window": [mjd_to_iso(t0), mjd_to_iso(t1)],
            "mjd_first": min(mjds), "mjd_last": max(mjds), "span_days": round(max(mjds) - min(mjds), 3),
            "n_exposures_in_window": len(inside), "n_points": len(points), "n_reliable": len(good),
            "unit": "mJy (aperture flux, r = 2 px, no aperture correction)", "time_standard": "UTC",
            "simultaneous": False,
            "caveats": ["not_simultaneous", "aperture_flux_no_correction", "quick_release_calibration",
                        "wcs_wave_table_wavelengths_about_1nm", "blended_sources_within_12_arcsec"],
            "points": points,
        }
        path.write_text(json.dumps(result), encoding="utf-8")
        report("done", 1.0, {"n_points": len(points)})
        return {"status": "done" if len(good) >= 3 else "insufficient_data", "result_id": key, "reused": False}
    finally:
        client.close()


def is_fresh(settings, result_id: str) -> bool:
    """Sonuç, arşiv sorgu önbelleğinin ömründen gençse yeniden kullanılır; arşiv güncellemeleri böylece yansır."""
    path = settings.processed_dir / "spectra" / f"{result_id}.json"
    return path.is_file() and (time.time() - path.stat().st_mtime) < settings.tap_cache_hours * 3600.0


def load_spectrum(settings, result_id: str) -> dict | None:
    path = settings.processed_dir / "spectra" / f"{result_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
