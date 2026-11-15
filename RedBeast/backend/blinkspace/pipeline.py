"""Uçtan uca hazırlama hattı.

Koordinatı doğrula → arşivi sorgula → görüntüleri seç → parçaları al → kaliteyi değerlendir → hizala →
önizlemeleri üret → sonucu kaydet.

Hazırlanmış bir dizi değişmezdir: kimliği, istek parametreleri + seçilen arşiv ürünlerinin parmak izi +
işlem sürümünden türetilir. Arşiv güncellenirse yeni bir dizi oluşur; eskisi (ve ona bağlı paylaşımlar)
olduğu gibi kalır.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import httpx
import numpy as np

from . import align, catalogs, preview, quality, selection
from .archive import Observation, dedupe, interruptible, query_observations
from .config import PIPELINE_VERSION, Settings
from .cutouts import CutoutError, RawStore, cutout_url
from .db import Database
from .spx import SpxFormatError, read_spx
from .wavelength import WaveModel

MIN_COVERAGE_FRAC = 0.6   # ızgaranın en az bu kadarı kare tarafından kapsanmalı
ALIGN_GMAX = 15.5         # hizalama denetiminde kullanılan Gaia yıldızları (G)


class Cancelled(Exception):
    pass


class InsufficientData(Exception):
    def __init__(self, reason: str, detail: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or {}


@dataclass(frozen=True)
class SearchParams:
    ra_deg: float
    dec_deg: float
    fov_arcmin: float = 6.0
    lam_um: float | None = None      # None: en iyi zaman kapsamına sahip dalga boyu grubu
    tol: float = 0.5                 # dalga boyu toleransı (bant genişliği kesri)
    max_frames: int = 8
    mjd_min: float | None = None
    mjd_max: float | None = None
    target_id: str | None = None     # hazır hedef (öngörülen konum katmanı için)

    def normalized(self) -> dict:
        return {
            "ra_deg": round(self.ra_deg % 360.0, 5),
            "dec_deg": round(self.dec_deg, 5),
            "fov_arcmin": round(self.fov_arcmin, 2),
            "lam_um": None if self.lam_um is None else round(self.lam_um, 4),
            "tol": round(self.tol, 3),
            "max_frames": int(self.max_frames),
            "mjd_min": None if self.mjd_min is None else round(self.mjd_min, 3),
            "mjd_max": None if self.mjd_max is None else round(self.mjd_max, 3),
            "target_id": self.target_id,
        }

    def request_key(self) -> str:
        doc = {"params": self.normalized(), "pipeline": PIPELINE_VERSION}
        return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:32]


def new_id(n: int = 10) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def mjd_to_iso(mjd: float) -> str:
    """MJD (UTC) -> ISO-8601 (saniye çözünürlüğü)."""
    days = math.floor(mjd)
    secs = int(round((mjd - days) * 86400.0))
    if secs >= 86400:
        days, secs = days + 1, secs - 86400
    # MJD 40587 = 1970-01-01
    t = time.gmtime((days - 40587) * 86400 + secs)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", t)


class Pipeline:
    def __init__(self, settings: Settings, db: Database, wave_model: WaveModel, targets: dict | None = None,
                 client_factory: Callable[[], httpx.Client] | None = None):
        self.settings = settings
        self.db = db
        self.model = wave_model
        self.targets = targets or {}
        self.store = RawStore(settings.raw_dir, db)
        self._client_factory = client_factory or (lambda: httpx.Client(
            timeout=settings.http_timeout_s, follow_redirects=True,
            headers={"User-Agent": f"BlinkSpace/{PIPELINE_VERSION} (SPHEREx blink viewer)"},
            limits=httpx.Limits(max_connections=settings.download_concurrency + 1),
        ))

    # ------------------------------------------------------------------ arşiv
    def observations(self, ra: float, dec: float, client: httpx.Client | None = None) -> tuple[list[Observation], list[Observation], dict]:
        """Konumu kapsayan kayıtlar (önbellekli) → (tekil, elenen kopyalar, sorgu bilgisi)."""
        key = f"{ra % 360.0:.4f},{dec:.4f}"
        cached = self.db.get_tap(key, self.settings.tap_cache_hours * 3600.0)
        if cached:
            obs = [Observation.from_dict(d) for d in cached["rows"]]
            meta = dict(cached["meta"], cached=True, queried_at=cached["fetched_at"])
        else:
            own = client is None
            client = client or self._client_factory()
            try:
                obs, meta = query_observations(ra, dec, self.settings.tap_url, self.settings.tap_timeout_s,
                                               self.settings.max_retries, client)
            finally:
                if own:
                    client.close()
            self.db.put_tap(key, meta, [o.to_dict() for o in obs])
            meta = dict(meta, cached=False, queried_at=time.time())
        kept, dropped = dedupe(obs)
        meta.update(n_unique=len(kept), n_reprocessed_dropped=len(dropped))
        return kept, dropped, meta

    def geometry(self, fov_arcmin: float) -> dict:
        half_diag_px = fov_arcmin * 60.0 / align.NATIVE_PIXSCALE_ARCSEC / 2.0 * math.sqrt(2.0)
        return {
            "cutout_size_deg": round(fov_arcmin / 60.0 * 1.45 + 0.012, 5),
            "min_edge_px": half_diag_px + 10.0,
        }

    def wavelength_options(self, ra: float, dec: float, fov_arcmin: float, tol: float, client=None) -> dict:
        kept, dropped, meta = self.observations(ra, dec, client)
        geo = self.geometry(fov_arcmin)
        cands, rejected = selection.build_candidates(kept, ra, dec, self.model, geo["min_edge_px"])
        groups = selection.find_groups(cands, tol)
        return {
            "archive": _archive_summary(meta),
            "n_candidates": len(cands),
            "n_rejected_edge": sum(1 for r in rejected if r["reason"] == "near_detector_edge"),
            "groups": [g.summary() for g in groups],
        }

    # ------------------------------------------------------------------ ana akış
    def run(self, params: SearchParams, report: Callable[[str, float, dict | None], None] | None = None,
            cancelled: Callable[[], bool] | None = None) -> dict:
        report = report or (lambda stage, progress, detail=None: None)
        cancelled = cancelled or (lambda: False)
        s = self.settings
        t_start = time.monotonic()
        timings: dict[str, float] = {}

        def check():
            if cancelled():
                raise Cancelled()
            if time.monotonic() - t_start > s.job_timeout_s:
                raise TimeoutError("job_timeout")

        client = self._client_factory()
        try:
            report("searching", 0.02, None)
            t0 = time.monotonic()
            # The archive can take a long time or be down: keep cancel and the job timeout alive while it is queried,
            # and say in the job's detail that we are waiting for it.
            with interruptible(check, lambda info: report("searching", 0.02, {"archive_wait": info})):
                kept, dropped, tap_meta = self.observations(params.ra_deg, params.dec_deg, client)
            timings["search_s"] = round(time.monotonic() - t0, 2)
            check()
            if not kept:
                raise InsufficientData("no_coverage", {"archive": _archive_summary(tap_meta)})

            geo = self.geometry(params.fov_arcmin)
            cands, rejected = selection.build_candidates(kept, params.ra_deg, params.dec_deg, self.model, geo["min_edge_px"])
            if not cands:
                raise InsufficientData("no_usable_frames", {"archive": _archive_summary(tap_meta), "n_rejected": len(rejected)})
            groups = selection.find_groups(cands, params.tol)
            if params.lam_um is not None:
                group = selection.group_at(cands, params.lam_um, params.tol)
                mode = "requested"
            else:
                group = groups[0]
                mode = "auto"
            chosen = selection.pick_frames(group, params.max_frames, params.mjd_min, params.mjd_max)
            group_summaries = [g.summary() for g in groups[:24]]
            if not chosen:
                raise InsufficientData("no_frames_at_wavelength", {
                    "archive": _archive_summary(tap_meta), "groups": group_summaries,
                    "lam_ref_um": group.lam_ref_um, "n_candidates": len(cands)})
            check()

            fingerprint = hashlib.sha256(json.dumps(
                sorted([c.obs.obs_id, c.obs.detector, c.obs.release, c.obs.l2_tag] for c in chosen)).encode()).hexdigest()[:24]
            request_key = params.request_key()
            sequence_key = hashlib.sha256(f"{request_key}:{fingerprint}".encode()).hexdigest()[:32]
            existing = self.db.get_sequence_by_key(sequence_key)
            if existing:
                report("done", 1.0, {"reused": True})
                return {"status": "done" if existing["status"] == "ready" else "insufficient_data",
                        "sequence_id": existing["id"], "reused": True}

            # ---------------------------------------------------------- indirme
            report("downloading", 0.1, {"n_frames": len(chosen), "n_done": 0})
            t0 = time.monotonic()
            urls = [cutout_url(s.irsa_base, c.obs.uri, params.ra_deg, params.dec_deg, geo["cutout_size_deg"]) for c in chosen]
            raws: dict[int, object] = {}
            dl_errors: list[dict] = []
            with ThreadPoolExecutor(max_workers=max(1, s.download_concurrency)) as pool:
                futs = {pool.submit(self.store.get, url, client, s.http_timeout_s, s.max_retries): i for i, url in enumerate(urls)}
                try:
                    for n_done, fut in enumerate(as_completed(futs), start=1):
                        i = futs[fut]
                        try:
                            raws[i] = fut.result()
                        except CutoutError as exc:
                            dl_errors.append({"obs_id": chosen[i].obs.obs_id, "detector": chosen[i].obs.detector, "reason": "download_failed", "error": str(exc)[:200]})
                        report("downloading", 0.1 + 0.5 * n_done / len(urls), {"n_frames": len(urls), "n_done": n_done})
                        check()
                except BaseException:
                    for f in futs:
                        f.cancel()
                    raise
            timings["download_s"] = round(time.monotonic() - t0, 2)
            timings["download_bytes"] = int(sum(r.size for r in raws.values() if not r.cached))
            timings["download_cached"] = int(sum(1 for r in raws.values() if r.cached))

            # ---------------------------------------------------------- hazırlama
            report("preparing", 0.62, None)
            t0 = time.monotonic()
            grid, shape = align.target_grid(params.ra_deg, params.dec_deg, params.fov_arcmin)
            prepared: list[dict] = []
            post_rejected: list[dict] = list(dl_errors)
            for i, cand in enumerate(chosen):
                check()
                raw = raws.get(i)
                if raw is None:
                    continue
                o = cand.obs
                try:
                    frame = read_spx(raw.path)
                except (SpxFormatError, OSError, ValueError) as exc:
                    post_rejected.append({"obs_id": o.obs_id, "detector": o.detector, "reason": "unreadable_fits", "error": str(exc)[:200]})
                    continue
                if frame.obs_id != o.obs_id or frame.detector != o.detector:
                    post_rejected.append({"obs_id": o.obs_id, "detector": o.detector, "reason": "header_mismatch",
                                          "error": f"{frame.obs_id}/D{frame.detector}"})
                    continue
                tx, ty = frame.world_to_pixel(params.ra_deg, params.dec_deg)
                tx, ty = float(tx[0]), float(ty[0])
                lam, bw = frame.wavelength_at(tx, ty)
                lam, bw = float(lam), float(bw)
                if not math.isfinite(lam) or abs(lam - group.lam_ref_um) > params.tol * group.bw_ref_um:
                    post_rejected.append({"obs_id": o.obs_id, "detector": o.detector, "reason": "wavelength_mismatch_after_download",
                                          "lam_um": None if not math.isfinite(lam) else round(lam, 5)})
                    continue
                aligned = align.reproject_frame(frame, grid, shape)
                cov = float(aligned.coverage.mean())
                if cov < MIN_COVERAGE_FRAC:
                    post_rejected.append({"obs_id": o.obs_id, "detector": o.detector, "reason": "low_coverage", "coverage": round(cov, 3)})
                    continue
                comparable = align.comparable_mask(aligned, group.lam_ref_um, group.bw_ref_um, params.tol)
                # arka plan: geçersiz + şüpheli + bilinen kaynak pikselleri dışarıda; yeterli piksel kalmazsa
                # kaynak maskesi bırakılır (çok parlak yıldız alanlarında tüm kesit SOURCE bayraklıdır).
                masks = quality.flag_masks(frame)
                src_frac = float(masks.source.mean())
                excl = aligned.invalid | aligned.suspect
                bkg_method = "sigma_clipped_median"
                if src_frac < 0.7:
                    from reproject import reproject_interp
                    src_al, _ = reproject_interp((masks.source.astype(float), frame.wcs), grid, shape_out=shape, order="nearest-neighbor")
                    excl = excl | (np.nan_to_num(src_al, nan=0.0) > 0.5)
                    bkg_method = "sigma_clipped_median_excluding_known_sources"
                bkg, sig, n_bkg = align.robust_background(aligned.image, excl)
                if not math.isfinite(bkg):
                    bkg, sig, n_bkg = align.robust_background(aligned.image, aligned.invalid)
                    bkg_method = "sigma_clipped_median"
                if not math.isfinite(bkg):
                    post_rejected.append({"obs_id": o.obs_id, "detector": o.detector, "reason": "no_valid_pixels"})
                    continue
                zodi_med = float(np.nanmedian(frame.zodi)) if frame.zodi is not None and np.isfinite(frame.zodi).any() else None
                q = quality.quality_summary(frame, (tx, ty))
                prepared.append({
                    "cand": cand, "raw": raw, "frame": frame, "aligned": aligned, "comparable": comparable,
                    "lam": lam, "bw": bw, "bkg": bkg, "sig": sig, "n_bkg": n_bkg, "bkg_method": bkg_method,
                    "zodi_med": zodi_med, "quality": q, "url": urls[i], "target_xy": (tx, ty),
                })
                report("preparing", 0.62 + 0.25 * (i + 1) / len(chosen), None)

            if not prepared:
                raise InsufficientData("all_frames_rejected", {
                    "archive": _archive_summary(tap_meta), "rejected": post_rejected, "groups": group_summaries})
            prepared.sort(key=lambda p: p["frame"].mjd_avg)

            limits = preview.display_limits([p["aligned"].image - p["bkg"] for p in prepared], [p["sig"] for p in prepared])
            seq_id = new_id()
            out_dir = s.processed_dir / seq_id
            out_dir.mkdir(parents=True, exist_ok=False)
            frames_meta: list[dict] = []
            common_valid = np.ones(shape, bool)
            common_comparable = np.ones(shape, bool)
            for idx, p in enumerate(prepared):
                al, fr, o = p["aligned"], p["frame"], p["cand"].obs
                sub = al.image - np.float32(p["bkg"])
                common_valid &= ~al.invalid
                common_comparable &= p["comparable"] & ~al.invalid
                png = f"frame_{idx:02d}.png"
                mask_png = f"frame_{idx:02d}_mask.png"
                npz = f"frame_{idx:02d}.npz"
                preview.write_gray_png(out_dir / png, sub, al.invalid, limits)
                preview.write_mask_png(out_dir / mask_png, al.suspect, ~p["comparable"] & ~al.invalid)
                np.savez_compressed(out_dir / npz, image=al.image, invalid=al.invalid, suspect=al.suspect,
                                    coverage=al.coverage, lam_um=al.lam_um, bw_um=al.bw_um, variance=al.variance,
                                    comparable=p["comparable"], background=np.float32(p["bkg"]))
                jyear = catalogs.mjd_to_jyear(fr.mjd_avg)
                fm = {
                    "index": idx,
                    "obs_id": fr.obs_id,
                    "detector": fr.detector,
                    "collection": o.collection,
                    "release": o.release,
                    "l2_tag": o.l2_tag,
                    "pipeline_version": fr.pipeline_version,
                    "timesys": fr.timesys,
                    "mjd_beg": fr.mjd_beg, "mjd_avg": fr.mjd_avg, "mjd_end": fr.mjd_end,
                    "date_avg": mjd_to_iso(fr.mjd_avg),
                    "epoch_jyear": round(jyear, 4),
                    "exposure_s": fr.exposure_s,
                    "lam_um": round(p["lam"], 5), "bw_um": round(p["bw"], 5),
                    "lam_pred_um": round(p["cand"].lam_um, 5),
                    "dlam_over_bw": round((p["lam"] - group.lam_ref_um) / group.bw_ref_um, 3),
                    "source_url": p["url"],
                    "archive_file_url": s.irsa_base.rstrip("/") + "/" + o.uri,
                    "archive_checksum": o.checksum,
                    "raw_sha256": p["raw"].sha256, "raw_size": p["raw"].size,
                    "quality": p["quality"],
                    "background": {"value_mjy_sr": round(p["bkg"], 5), "sigma_mjy_sr": round(p["sig"], 5),
                                   "n_pixels": p["n_bkg"], "method": p["bkg_method"],
                                   "zodi_model_median_mjy_sr": None if p["zodi_med"] is None else round(p["zodi_med"], 5)},
                    "coverage_frac": round(float(al.coverage.mean()), 4),
                    "invalid_frac": round(float(al.invalid.mean()), 4),
                    "suspect_frac": round(float(al.suspect.mean()), 4),
                    "comparable_frac": round(float((p["comparable"] & ~al.invalid).mean()), 4),
                    "lam_range_um": [round(float(np.nanmin(al.lam_um)), 5), round(float(np.nanmax(al.lam_um)), 5)],
                    "psf_fwhm_arcsec": fr.psf_fwhm_arcsec, "psf_kind": fr.psf_kind,
                    "cutout_wcs": {"crval": [float(v) for v in fr.wcs.wcs.crval], "crpix": [float(v) for v in fr.wcs.wcs.crpix],
                                   "pc": [[float(v) for v in row] for row in fr.wcs.wcs.get_pc()], "ctype": list(fr.wcs.wcs.ctype),
                                   "det_origin": [fr.det_origin[0], fr.det_origin[1]]},
                    "png": png, "mask_png": mask_png, "npz": npz,
                }
                tgt = self.targets.get(params.target_id or "")
                if tgt:
                    pr, pd = catalogs.propagate(tgt["ra_deg"], tgt["dec_deg"], tgt.get("pmra_masyr"), tgt.get("pmdec_masyr"),
                                                tgt.get("epoch_jyear", 2000.0), jyear)
                    fm["target_predicted"] = {"ra": round(pr, 6), "dec": round(pd, 6), "method": "proper_motion_only"}
                frames_meta.append(fm)
            timings["prepare_s"] = round(time.monotonic() - t0, 2)

            report("preparing", 0.9, {"step": "alignment_check"})
            alignment = self._alignment_check(params, prepared, grid, shape, client)
            visits = selection.split_visits([p["cand"] for p in prepared])
            mjds = [f["mjd_avg"] for f in frames_meta]
            warnings: list[str] = []
            status = "ready"
            if len(frames_meta) < 2:
                status = "insufficient"
                warnings.append("single_frame")
            elif len(visits) < 2:
                warnings.append("single_visit")
            if post_rejected:
                warnings.append("partial_data")
            if any(f["quality"].get("target", {}).get("saturated") for f in frames_meta):
                warnings.append("center_saturated")
            meta = {
                "id": seq_id,
                "status": status,
                "pipeline_version": PIPELINE_VERSION,
                "created_at": time.time(),
                "center": {"ra_deg": params.ra_deg % 360.0, "dec_deg": params.dec_deg, "frame": "ICRS"},
                "grid": align.grid_to_dict(grid, shape),
                "wavelength": {"lam_ref_um": round(group.lam_ref_um, 5), "bw_ref_um": round(group.bw_ref_um, 5),
                               "tol": params.tol, "mode": mode, "groups": group_summaries,
                               "group_n_frames": len(group.members), "group_n_visits": len(group.visits)},
                "display": dict(limits, unit="MJy/sr", background_subtracted=True),
                "archive": _archive_summary(tap_meta),
                "selection": {"n_observations": len(kept), "n_reprocessed_dropped": len(dropped), "n_candidates": len(cands),
                              "n_rejected_edge": sum(1 for r in rejected if r["reason"] == "near_detector_edge"),
                              "n_selected": len(chosen), "n_prepared": len(frames_meta), "rejected_after_download": post_rejected,
                              "cutout_size_deg": geo["cutout_size_deg"], "min_edge_px": round(geo["min_edge_px"], 1)},
                "n_frames": len(frames_meta),
                "n_visits": len(visits),
                "mjd_first": min(mjds), "mjd_last": max(mjds), "span_days": round(max(mjds) - min(mjds), 3),
                "common_valid_frac": round(float(common_valid.mean()), 4),
                "common_comparable_frac": round(float(common_comparable.mean()), 4),
                "alignment": alignment,
                "warnings": warnings,
                "data_fingerprint": fingerprint,
                "timings": timings,
                "target_id": params.target_id,
            }
            (out_dir / "sequence.json").write_text(json.dumps({"meta": meta, "frames": frames_meta}, indent=1), encoding="utf-8")
            self.db.put_sequence(seq_id, sequence_key, request_key, status, params.normalized(), meta, frames_meta)
            report("done", 1.0, {"n_frames": len(frames_meta)})
            return {"status": "done" if status == "ready" else "insufficient_data", "sequence_id": seq_id, "reused": False,
                    "reason": None if status == "ready" else "single_frame"}
        finally:
            client.close()

    # ------------------------------------------------------------------ hizalama denetimi
    def gaia(self, ra: float, dec: float, radius_deg: float, client=None) -> list[dict]:
        key = f"gaia:{ra:.4f},{dec:.4f},{radius_deg:.4f}"
        if os.environ.get("BLINKSPACE_GAIA_PROVIDER", "irsa") != "irsa":
            key += ":" + os.environ["BLINKSPACE_GAIA_PROVIDER"]      # cached rows carry their own mirror's provenance
        cached = self.db.get_catalog(key, 30 * 86400.0)
        if cached is not None:
            return cached
        rows = catalogs.query_gaia(self.settings.tap_url, ra, dec, radius_deg, 18.0, 120.0, client)
        self.db.put_catalog(key, rows)
        return rows

    def allwise(self, ra: float, dec: float, radius_deg: float, client=None) -> list[dict]:
        key = f"allwise:{ra:.4f},{dec:.4f},{radius_deg:.4f}"
        if os.environ.get("BLINKSPACE_ALLWISE_PROVIDER", "irsa") != "irsa":
            key += ":" + os.environ["BLINKSPACE_ALLWISE_PROVIDER"]
        cached = self.db.get_catalog(key, 30 * 86400.0)
        if cached is not None:
            return cached
        rows = catalogs.query_allwise(self.settings.tap_url, ra, dec, radius_deg, 120.0, client)
        self.db.put_catalog(key, rows)
        return rows

    def _alignment_check(self, params: SearchParams, prepared: list[dict], grid, shape, client) -> dict:
        """Gaia DR3 yıldızlarının (kare dönemine ilerletilmiş) öngörülen konumu ile hizalanmış karede ölçülen
        merkezler arasındaki artıklar. Hareketi aranan hedefe dokunmaz; yalnızca WCS hizalamasını denetler."""
        radius = params.fov_arcmin / 60.0 / 2.0 * 1.2
        try:
            stars = self.gaia(params.ra_deg, params.dec_deg, radius, client)
        except Exception as exc:  # katalog erişimi dizi üretimini engellemez
            return {"status": "unavailable", "reason": str(exc)[:160]}
        bright = [st for st in stars if st["g"] is not None and st["g"] <= ALIGN_GMAX]
        per_frame = []
        all_de, all_dn = [], []
        scale = align.NATIVE_PIXSCALE_ARCSEC
        for idx, p in enumerate(prepared):
            jyear = catalogs.mjd_to_jyear(p["frame"].mjd_avg)
            pos = [catalogs.propagate(st["ra"], st["dec"], st["pmra"], st["pmdec"], catalogs.GAIA_REF_EPOCH, jyear) for st in stars]
            if pos:
                xs, ys = grid.all_world2pix([q[0] for q in pos], [q[1] for q in pos], 0)
            else:
                xs, ys = np.array([]), np.array([])
            de, dn = [], []
            img = p["aligned"].image - np.float32(p["bkg"])
            sus = p["aligned"].suspect
            for j, st in enumerate(stars):
                if st["g"] is None or st["g"] > ALIGN_GMAX:
                    continue
                x0, y0 = float(xs[j]), float(ys[j])
                # yalıtılmışlık: 4 piksel içinde 3 kadirden az sönük başka yıldız olmamalı
                crowded = any(k != j and stars[k]["g"] is not None and stars[k]["g"] < st["g"] + 3.0
                              and (xs[k] - x0) ** 2 + (ys[k] - y0) ** 2 < 16.0 for k in range(len(stars)))
                if crowded:
                    continue
                c = align.centroid(img, x0, y0, half=2)
                if c is None:
                    continue
                ix, iy = int(round(x0)), int(round(y0))
                if sus[iy - 2: iy + 3, ix - 2: ix + 3].any():
                    continue
                if c[2] < 25.0 * p["sig"]:
                    continue
                de.append(-(c[0] - x0) * scale)   # +x batı yönü: doğu artığı = -dx
                dn.append((c[1] - y0) * scale)
            entry = {"index": idx, "n_stars": len(de)}
            if de:
                entry.update(median_de_arcsec=round(float(np.median(de)), 2), median_dn_arcsec=round(float(np.median(dn)), 2),
                             rms_arcsec=round(float(np.sqrt(np.mean(np.square(de) + np.square(dn)))), 2))
                all_de += de
                all_dn += dn
            per_frame.append(entry)
        out = {"status": "ok" if all_de else "no_reference_stars", "catalog": "Gaia DR3",
               "catalogue_providers": sorted({st.get("source_url", self.settings.tap_url) for st in stars}),
               "n_catalog_stars": len(stars), "n_bright": len(bright), "gmax": ALIGN_GMAX, "per_frame": per_frame,
               "method": "flux-weighted centroid in 5x5 px box vs Gaia position propagated by proper motion to frame epoch"}
        if all_de:
            out.update(n_measurements=len(all_de),
                       median_de_arcsec=round(float(np.median(all_de)), 2), median_dn_arcsec=round(float(np.median(all_dn)), 2),
                       rms_arcsec=round(float(np.sqrt(np.mean(np.square(all_de) + np.square(all_dn)))), 2),
                       pixel_scale_arcsec=scale)
        return out


def _archive_summary(meta: dict) -> dict:
    return {
        "service": meta.get("service", "IRSA TAP"),
        "tap_url": meta.get("tap_url"),
        "adql": meta.get("adql"),
        "queried_at": meta.get("queried_at"),
        "from_cache": bool(meta.get("cached")),
        "elapsed_s": meta.get("elapsed_s"),
        "n_rows": meta.get("rows"),
        "n_parsed": meta.get("parsed"),
        "n_unique": meta.get("n_unique"),
        "n_reprocessed_dropped": meta.get("n_reprocessed_dropped"),
        **({"inventory_source": meta["inventory_source"]} if "inventory_source" in meta else {}),
        **({"sia_requests": meta["sia_requests"]} if "sia_requests" in meta else {}),
        **({"tap_fallback_reason": meta["tap_fallback_reason"]} if "tap_fallback_reason" in meta else {}),
    }
