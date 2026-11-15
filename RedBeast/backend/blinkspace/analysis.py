"""İleri analizler: fark görüntüsü, birleştirme, ışık eğrisi, katalog katmanı, aday önerisi.

Hepsi hazırlanmış bir dizi üzerinde çalışır; dolayısıyla kareler zaten dalga boyu uyumlu, ortak ızgaraya
hizalı ve arka planı kaydedilmiş durumdadır. Her çıktı kendi sınırlarını (`caveats`) taşır.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import align, catalogs, preview
from .config import Settings
from .cutouts import RawStore
from .db import Database
from .photometry import aperture_photometry
from .spx import read_spx

QUANT_TOL = 0.25          # nicel karşılaştırma için dalga boyu toleransı (bant genişliği kesri)
MIN_COMMON_PIXELS = 50
MAX_ALIGNMENT_RMS_ARCSEC = 0.3 * align.NATIVE_PIXSCALE_ARCSEC
CAND_SNR = 6.0            # aday eşiği (fark görüntüsünde σ)
CAND_MIN_FRAC = 0.25      # yerel akıya göre en küçük kesirsel değişim
CAND_PAIR_PX = 4.0        # hareket çifti (artı/eksi) için en büyük ayrıklık (piksel)


class AnalysisError(ValueError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def comparable_pixels(frame: dict) -> np.ndarray:
    return ~frame["invalid"] & frame["comparable"]


class Analysis:
    def __init__(self, settings: Settings, db: Database, pipeline):
        self.s = settings
        self.db = db
        self.pipeline = pipeline
        self.store = RawStore(settings.raw_dir, db)

    def _dir(self, seq: dict) -> Path:
        return self.s.processed_dir / seq["id"]

    def _frame(self, seq: dict, idx: int) -> dict:
        if not (0 <= idx < len(seq["frames"])):
            raise AnalysisError("bad_frame_index")
        with np.load(self._dir(seq) / seq["frames"][idx]["npz"]) as z:
            return {k: z[k] for k in z.files}

    @staticmethod
    def _sub(fr: dict) -> np.ndarray:
        return fr["image"].astype(np.float64) - float(fr["background"])

    # ------------------------------------------------------------------ fark
    def _difference(self, seq: dict, a: int, b: int):
        if a == b:
            raise AnalysisError("same_frame")
        fa, fb = self._frame(seq, a), self._frame(seq, b)
        invalid = ~(comparable_pixels(fa) & comparable_pixels(fb))
        d = np.where(invalid, np.nan, self._sub(fb) - self._sub(fa))
        vals = d[np.isfinite(d)]
        if vals.size < MIN_COMMON_PIXELS:
            raise AnalysisError("no_common_area")
        sigma = 1.4826 * float(np.median(np.abs(vals - np.median(vals))))
        return fa, fb, d, invalid, sigma

    def diff(self, seq: dict, a: int, b: int) -> dict:
        fa, fb, d, invalid, sigma = self._difference(seq, a, b)
        ma, mb = seq["frames"][a], seq["frames"][b]
        name = f"diff_{a:02d}_{b:02d}.png"
        scale = 10.0 * sigma if sigma > 0 else 1.0
        path = self._dir(seq) / name
        if not path.exists():
            preview.write_diff_png(path, d, invalid, scale)
        caveats = ["no_psf_matching", "undersampled_psf_residuals"]
        fw_a, fw_b = ma.get("psf_fwhm_arcsec"), mb.get("psf_fwhm_arcsec")
        if fw_a and fw_b and abs(fw_a - fw_b) / max(fw_a, fw_b) > 0.15:
            caveats.append("psf_fwhm_differs")
        if abs(ma["dlam_over_bw"] - mb["dlam_over_bw"]) > QUANT_TOL:
            caveats.append("wavelength_offset_above_quantitative_tolerance")
        al = seq["meta"].get("alignment", {})
        if al.get("status") != "ok":
            caveats.append("alignment_not_verified")
        elif al.get("rms_arcsec", 0) > MAX_ALIGNMENT_RMS_ARCSEC:
            caveats.append("alignment_residual_large")
        return {
            "file": name, "a": a, "b": b, "definition": "B − A (arka planı çıkarılmış, MJy/sr)",
            "dt_days": round(mb["mjd_avg"] - ma["mjd_avg"], 4),
            "lam_a_um": ma["lam_um"], "lam_b_um": mb["lam_um"],
            "sigma_mjy_sr": round(sigma, 5), "display_scale_mjy_sr": round(scale, 5),
            "valid_frac": round(float((~invalid).mean()), 4),
            "psf_fwhm_arcsec": [fw_a, fw_b], "caveats": caveats,
        }

    # ------------------------------------------------------------------ birleştirme
    def stack(self, seq: dict) -> dict:
        n = len(seq["frames"])
        if n < 2:
            raise AnalysisError("need_two_frames")
        cube, ok = [], []
        for i in range(n):
            f = self._frame(seq, i)
            good = ~f["invalid"] & f["comparable"]
            cube.append(np.where(good, self._sub(f), np.nan))
            ok.append(good)
        cube = np.array(cube)
        count = np.sum(ok, axis=0)
        need = max(2, math.ceil(0.5 * n))
        with np.errstate(invalid="ignore"):
            mean = np.nansum(cube, axis=0) / np.maximum(count, 1)
        invalid = count < need
        mean = np.where(invalid, np.nan, mean)
        name = "stack.png"
        path = self._dir(seq) / name
        if not path.exists():
            preview.write_gray_png(path, mean, invalid, seq["meta"]["display"])
        caveats = ["moving_sources_blur", "variable_sources_averaged"]
        blur = None
        tp = [f.get("target_predicted") for f in seq["frames"]]
        if all(tp):
            from .coords import angular_separation_deg
            blur = angular_separation_deg(tp[0]["ra"], tp[0]["dec"], tp[-1]["ra"], tp[-1]["dec"]) * 3600.0 / align.NATIVE_PIXSCALE_ARCSEC
        spread = max(abs(f["dlam_over_bw"]) for f in seq["frames"])
        return {
            "file": name, "n_frames": n, "min_frames_per_pixel": need, "method": "mean of background-subtracted, wavelength-comparable valid pixels",
            "valid_frac": round(float((~invalid).mean()), 4),
            "max_dlam_over_bw": round(spread, 3),
            "target_motion_px": None if blur is None else round(blur, 2),
            "span_days": seq["meta"]["span_days"], "caveats": caveats,
        }

    def _track_stack_arrays(self, seq: dict):
        """Display-only co-moving mean; invalid pixels never contribute as zero."""
        from astropy.wcs import WCS

        predictions = [f.get("target_predicted") for f in seq["frames"]]
        if not predictions or not all(p and all(isinstance(p.get(k), (int, float)) and math.isfinite(p[k])
                                                for k in ("ra", "dec")) for p in predictions):
            raise AnalysisError("no_target_track")
        if len(predictions) < 2:
            raise AnalysisError("need_two_frames")
        g = seq["meta"]["grid"]
        w = WCS(naxis=2)
        w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        w.wcs.crval, w.wcs.crpix, w.wcs.cdelt = g["crval"], g["crpix"], g["cdelt"]
        x, y = w.all_world2pix([p["ra"] for p in predictions], [p["dec"] for p in predictions], 0)
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise AnalysisError("no_target_track")
        reference = 0
        shifts = [[float(x[reference] - px), float(y[reference] - py)] for px, py in zip(x, y)]
        total = np.zeros((g["ny"], g["nx"]), dtype=np.float64)
        count = np.zeros(total.shape, dtype=np.int16)
        for i, (dx, dy) in enumerate(shifts):
            frame = self._frame(seq, i)
            value = self._sub(frame)
            good = ~frame["invalid"] & frame["comparable"] & np.isfinite(value)
            weight = ndimage.shift(good.astype(np.float64), (dy, dx), order=1, mode="constant", cval=0, prefilter=False)
            shifted = ndimage.shift(np.where(good, value, 0.0), (dy, dx), order=1, mode="constant", cval=0, prefilter=False)
            valid = weight > 0.999
            # Weighting is only an interpolation device, not a missing-pixel fill.
            total += np.where(valid, shifted / np.maximum(weight, 1e-12), 0.0)
            count += valid
        need = math.ceil(len(predictions) / 2)
        invalid = count < need
        mean = np.where(invalid, np.nan, total / np.maximum(count, 1))
        return mean, invalid, shifts, reference

    def track_stack(self, seq: dict) -> dict:
        mean, invalid, shifts, reference = self._track_stack_arrays(seq)
        name = "track_stack.png"
        path = self._dir(seq) / name
        if not path.exists():
            preview.write_gray_png(path, mean, invalid, seq["meta"]["display"])
        return {"file": name, "shifts_px": shifts, "shift_axes": ["x", "y"], "reference_index": reference,
                "valid_frac": round(float((~invalid).mean()), 4),
                "method": "mean after predicted-target bilinear shifts; validity weight > 0.999; ceil(n/2) valid frames per pixel",
                "caveats": ["static_sources_smeared", "proper_motion_only_no_parallax", "display_product_not_photometry"]}

    # ------------------------------------------------------------------ ışık eğrisi
    def lightcurve(self, seq: dict, ra: float | None, dec: float | None, follow_target: bool) -> dict:
        key = "target" if follow_target else f"{ra:.5f}_{dec:.5f}"
        cache = self._dir(seq) / f"lightcurve_{key}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        pts = []
        for f in seq["frames"]:
            if follow_target:
                tp = f.get("target_predicted")
                if not tp:
                    raise AnalysisError("no_target_prediction")
                pra, pdec = tp["ra"], tp["dec"]
            else:
                pra, pdec = ra, dec
            rec = self.db.get_raw(f["source_url"])
            if not rec or rec["sha256"] != f["raw_sha256"]:
                raise AnalysisError("raw_file_missing")
            frame = read_spx(self.store.path_for(rec["sha256"]))
            ph = aperture_photometry(frame, pra, pdec)
            pts.append({"index": f["index"], "mjd": f["mjd_avg"], "date": f["date_avg"], "obs_id": f["obs_id"],
                        "detector": f["detector"], "ra": pra, "dec": pdec, **ph})
        lams = [p["lam_um"] for p in pts if p["lam_um"] is not None]
        bws = [p["bw_um"] for p in pts if p["bw_um"] is not None]
        lam_ref = float(np.median(lams)) if lams else None
        bw_ref = float(np.median(bws)) if bws else None
        for p in pts:
            p["dlam_over_bw"] = None if (lam_ref is None or p["lam_um"] is None) else round((p["lam_um"] - lam_ref) / bw_ref, 3)
            p["quantitative_ok"] = bool(p["valid"] and p.get("reliable") and p["dlam_over_bw"] is not None and abs(p["dlam_over_bw"]) <= QUANT_TOL)
        out = {
            "position_mode": "follows_predicted_target" if follow_target else "fixed_sky_position",
            "lam_ref_um": None if lam_ref is None else round(lam_ref, 5), "bw_ref_um": None if bw_ref is None else round(bw_ref, 5),
            "quantitative_tolerance": QUANT_TOL, "unit": "mJy (aperture flux, no aperture correction)",
            "time_standard": "UTC", "points": pts,
            "caveats": ["aperture_flux_no_correction", "psf_varies_between_frames", "quick_release_calibration",
                        "single_wavelength_group_only"],
        }
        cache.write_text(json.dumps(out), encoding="utf-8")
        return out

    # ------------------------------------------------------------------ katalog katmanı
    def overlay(self, seq: dict, catalog: str) -> dict:
        c = seq["meta"]["center"]
        radius = seq["meta"]["grid"]["nx"] * seq["meta"]["grid"]["pixscale_arcsec"] / 3600.0 / 2.0 * 1.45
        if catalog == "gaia":
            stars = self.pipeline.gaia(c["ra_deg"], c["dec_deg"], round(radius, 4))
            epochs = [f["epoch_jyear"] for f in seq["frames"]]
            mid = float(np.mean(epochs))
            src = []
            for st in sorted(stars, key=lambda s: s["g"] if s["g"] is not None else 99)[:400]:
                ra, dec = catalogs.propagate(st["ra"], st["dec"], st["pmra"], st["pmdec"], catalogs.GAIA_REF_EPOCH, mid)
                pm = None if st["pmra"] is None else math.hypot(st["pmra"], st["pmdec"])
                item = {"id": st["id"], "ra": round(ra, 6), "dec": round(dec, 6), "mag": st["g"], "pm_masyr": None if pm is None else round(pm, 1)}
                if pm is not None and pm > 200.0:
                    item["per_frame"] = [[round(v, 6) for v in catalogs.propagate(st["ra"], st["dec"], st["pmra"], st["pmdec"], catalogs.GAIA_REF_EPOCH, e)] for e in epochs]
                src.append(item)
            return {"catalog": "Gaia DR3", "type": "catalog", "band": "G (optik)", "catalog_epoch": catalogs.GAIA_REF_EPOCH,
                    "shown_epoch": round(mid, 3), "resolution_note": "Gaia ≈0.4″ çözer; SPHEREx pikseli 6.15″",
                    "propagation": "proper_motion_only", "n": len(src), "sources": src}
        if catalog == "allwise":
            rows = self.pipeline.allwise(c["ra_deg"], c["dec_deg"], round(radius, 4))
            src = [{"id": r["id"], "ra": r["ra"], "dec": r["dec"], "mag": r["w2"] if r["w2"] is not None else r["w1"], "w1": r["w1"], "w2": r["w2"]}
                   for r in sorted(rows, key=lambda r: r["w1"] if r["w1"] is not None else 99)[:400]]
            return {"catalog": "AllWISE", "type": "catalog", "band": "W1 3.4 µm / W2 4.6 µm", "catalog_epoch": catalogs.ALLWISE_MEAN_EPOCH,
                    "shown_epoch": catalogs.ALLWISE_MEAN_EPOCH, "resolution_note": "WISE ≈6″ çözünürlük; konumlar ≈2010.5 dönemine aittir",
                    "propagation": "none", "n": len(src), "sources": src}
        raise AnalysisError("unknown_catalog")

    # ------------------------------------------------------------------ aday önerisi
    def candidates(self, seq: dict, a: int, b: int) -> dict:
        fa, fb, d, invalid, sigma = self._difference(seq, a, b)
        grid = seq["meta"]["grid"]
        out = detect_changes(self._sub(fa), self._sub(fb), d, invalid, fa["suspect"] | fb["suspect"], sigma)
        w, _ = align.target_grid(grid["crval"][0], grid["crval"][1], grid["nx"] * grid["pixscale_arcsec"] / 60.0)
        for c in out["candidates"]:
            ra, dec = w.all_pix2world([c["x"]], [c["y"]], 0)
            c["ra"], c["dec"] = round(float(ra[0]), 6), round(float(dec[0]), 6)
            if "x_from" in c:
                r0, d0 = w.all_pix2world([c["x_from"]], [c["y_from"]], 0)
                c["ra_from"], c["dec_from"] = round(float(r0[0]), 6), round(float(d0[0]), 6)
        out.update(a=a, b=b, sigma_mjy_sr=round(sigma, 5), status="review_aid_not_a_discovery",
                   method=f"|B−A| ≥ {CAND_SNR}σ bağlı bölgeler; yerel akıya oranı ≥ {CAND_MIN_FRAC}; "
                          f"{CAND_PAIR_PX} piksel içindeki artı/eksi çifti = olası hareket",
                   caveats=["no_psf_matching", "undersampled_psf_residuals", "cosmic_rays_and_artifacts_possible"])
        return out


def detect_changes(a: np.ndarray, b: np.ndarray, d: np.ndarray, invalid: np.ndarray, suspect: np.ndarray, sigma: float) -> dict:
    """Açıklanabilir değişim adayları (inceleme yardımı).

    1. S/N = (B − A)/σ; |S/N| ≥ CAND_SNR olan pikseller artı ve eksi için ayrı bağlı bölgelere ayrılır.
    2. Tepe çevresindeki 5×5 kutu akıları (A ve B) karşılaştırılır: |ΣB − ΣA| / max(ΣA, ΣB); oran CAND_MIN_FRAC
       altındaysa atılır (durağan yıldızın PSF/piksel-fazı artığı: toplam akı değişmemiştir).
    3. Şüpheli bayraklı piksele değen bölgeler "olası görüntü hatası" olarak etiketlenir.
    4. CAND_PAIR_PX içinde bir artı ve bir eksi bölge varsa çift "olası hareket" (eksi → artı yönünde) sayılır;
       kalanlar "olası parlaklık değişimi"dir.
    """
    if not (sigma > 0):
        return {"candidates": [], "n_raw": 0, "n_dropped_low_fraction": 0}
    snr = np.where(invalid, 0.0, np.nan_to_num(d, nan=0.0) / sigma)
    sus = ndimage.binary_dilation(suspect, iterations=1)
    # 5×5 kutu toplamları: PSF genişliği ve piksel fazı farklarına tek pikselden çok daha az duyarlıdır.
    k = np.ones((5, 5))
    box_bad = ndimage.maximum_filter(invalid.astype(np.uint8), size=5) > 0
    abox = ndimage.convolve(np.where(invalid, 0.0, np.nan_to_num(a, nan=0.0)), k, mode="constant")
    bbox = ndimage.convolve(np.where(invalid, 0.0, np.nan_to_num(b, nan=0.0)), k, mode="constant")
    floor = 5.0 * sigma * 5.0  # kutu toplamı için 5σ·√25 gürültü tabanı
    comps = []
    n_raw = dropped = 0
    for sign in (1, -1):
        lab, n = ndimage.label(sign * snr >= CAND_SNR)
        for i in range(1, n + 1):
            reg = lab == i
            n_raw += 1
            peak = np.unravel_index(np.argmax(np.where(reg, sign * snr, -np.inf)), snr.shape)
            pk = float(abs(snr[peak]))
            if reg.sum() < 2 and pk < 10.0:
                dropped += 1
                continue
            if box_bad[peak]:
                # kutuda ölçüm olmayan piksel var: akı karşılaştırılamaz -> görüntü hatası adayı
                frac = float("inf")
            else:
                sa, sb = float(abox[peak]), float(bbox[peak])
                frac = abs(sb - sa) / max(sa, sb, floor)
                if frac < CAND_MIN_FRAC:
                    dropped += 1
                    continue
            wts = np.where(reg, np.abs(np.nan_to_num(d, nan=0.0)), 0.0)
            yy, xx = np.mgrid[0:snr.shape[0], 0:snr.shape[1]]
            cx, cy = float((wts * xx).sum() / wts.sum()), float((wts * yy).sum() / wts.sum())
            comps.append({"sign": sign, "x": cx, "y": cy, "snr": pk, "frac": frac, "npix": int(reg.sum()),
                          "artifact": bool(np.any(sus & reg)) or bool(box_bad[peak])})
    cands, used = [], set()
    pos = [c for c in comps if c["sign"] > 0 and not c["artifact"]]
    neg = [c for c in comps if c["sign"] < 0 and not c["artifact"]]
    for p in sorted(pos, key=lambda c: -c["snr"]):
        best, bd = None, CAND_PAIR_PX
        for q in neg:
            if id(q) in used:
                continue
            dist = math.hypot(p["x"] - q["x"], p["y"] - q["y"])
            if dist <= bd:
                best, bd = q, dist
        if best is not None:
            used.add(id(best))
            used.add(id(p))
            cands.append({"classification": "possible_motion", "x": round(p["x"], 2), "y": round(p["y"], 2),
                          "x_from": round(best["x"], 2), "y_from": round(best["y"], 2), "shift_px": round(bd, 2),
                          "snr": round(min(p["snr"], best["snr"]), 1), "frac_change": round(min(p["frac"], best["frac"]), 2),
                          "explanation": "paired_negative_and_positive_residuals"})
    for c in comps:
        if id(c) in used:
            continue
        if c["artifact"]:
            cls, expl = "possible_artifact", "touches_flagged_pixels"
        else:
            cls, expl = "possible_brightness_change", "brightened" if c["sign"] > 0 else "faded"
        cands.append({"classification": cls, "x": round(c["x"], 2), "y": round(c["y"], 2), "snr": round(c["snr"], 1),
                      "frac_change": None if not math.isfinite(c["frac"]) else round(c["frac"], 2), "explanation": expl})
    cands.sort(key=lambda c: -c["snr"])
    return {"candidates": cands[:20], "n_raw": n_raw, "n_dropped_low_fraction": dropped}
