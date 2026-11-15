"""Hazırlanmış bir dizide hedefin ölçülmesi: seçilebilirlik, konum, hareket ve parlaklık.

Raporlar ve öğretici görevlerin yanıt anahtarı bu modülün **gerçek veriden** ürettiği sayılara dayanır.
Durum basamakları birbirinden ayrı tutulur:
  data_available → source_detected → change_seen → (bilimsel doğrulama: bu araçla iddia edilmez)
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import align
from .coords import angular_separation_deg
from .photometry import aperture_photometry
from .spx import read_spx

DETECT_SNR = 5.0
CENTROID_ERR_PX = 0.3   # doymuş çekirdek öbeğinin merkezi için varsayılan tek kare belirsizliği (piksel)
CENTROID_FLOOR_PX = 0.1  # akı-ağırlıklı merkez için taban belirsizlik (piksel)
QUANT_TOL = 0.25         # nicel karşılaştırma toleransı (bant genişliği kesri)
CHANGE_SIGMA = 3.0        # "değişim görülüyor" eşiği (hareket ve parlaklık için aynı)
MIN_BRIGHTNESS_RATIO = 1.2
VISUAL_TOL_SYSTEMATIC = 0.10   # 0.25–0.5 arası dalga boyu kayması kabul edilirse eklenen temkinli sistematik (kesir)


def _offsets_arcsec(ra, dec, ra0, dec0):
    """(doğu, kuzey) yay saniyesi: (ra, dec) − (ra0, dec0)."""
    de = (ra - ra0) * math.cos(math.radians(dec0)) * 3600.0
    dn = (dec - dec0) * 3600.0
    return de, dn


def measure_frame(analysis, seq: dict, idx: int, ra: float, dec: float) -> dict:
    """Bir karede (ra, dec) çevresindeki kaynağı ölçer (hizalanmış ızgarada merkez + ham piksellerde akı)."""
    f = seq["frames"][idx]
    fr = analysis._frame(seq, idx)
    g = seq["meta"]["grid"]
    grid, shape = align.target_grid(g["crval"][0], g["crval"][1], g["nx"] * g["pixscale_arcsec"] / 60.0)
    x0, y0 = (float(v[0]) for v in grid.all_world2pix([ra], [dec], 0))
    img = fr["image"].astype(np.float64) - float(fr["background"])
    out = {"index": idx, "date": f["date_avg"], "mjd": f["mjd_avg"], "lam_um": f["lam_um"], "pred_ra": ra, "pred_dec": dec,
           "method": None, "ra": None, "dec": None, "offset_e_arcsec": None, "offset_n_arcsec": None}
    ny, nx = img.shape
    if not (3 <= x0 < nx - 3 and 3 <= y0 < ny - 3):
        out["method"] = "off_grid"
        out["snr"] = None
        out["photometry"] = {"valid": False, "reason": "off_grid", "flux_mjy": None, "err_mjy": None,
                             "saturated": False, "reliable": False, "flags": [], "lam_um": None, "bw_um": None}
        return out
    # ham piksellerde açıklık fotometrisi (öngörülen konumda)
    rec = analysis.db.get_raw(f["source_url"])
    frame = read_spx(analysis.store.path_for(rec["sha256"]))
    ph = aperture_photometry(frame, ra, dec)
    out["photometry"] = {k: ph.get(k) for k in ("valid", "reason", "flux_mjy", "err_mjy", "saturated", "reliable", "flags", "lam_um", "bw_um")}
    out["snr"] = None if not ph["valid"] or not ph["err_mjy"] else round(ph["flux_mjy"] / ph["err_mjy"], 1)

    # 1) doymuş çekirdek: öngörülen konumun kendisi (1 piksel içinde) geçersizse ve açıklıkta doyma bayrağı
    #    (OVERFLOW/NONLINEAR) varsa, o geçersiz öbeğin merkezi. İlgisiz öbekler (kozmik ışın vb.) hedef sayılmaz.
    yy, xx = np.mgrid[0:ny, 0:nx]
    at_target = (xx - x0) ** 2 + (yy - y0) ** 2 <= 1.0
    cx = cy = None
    if (fr["invalid"] & at_target).any():
        lab, _ = ndimage.label(fr["invalid"])
        ids = np.unique(lab[fr["invalid"] & at_target])
        reg = np.isin(lab, ids[ids > 0])
        if ph["saturated"] and reg.sum() >= 4:
            cx, cy = float(xx[reg].mean()), float(yy[reg].mean())
            out["method"] = "saturated_core_centroid"
            out["n_core_pixels"] = int(reg.sum())
        else:
            out["method"] = "invalid_pixels_at_target"      # ölçüm yok: konum da akı da kullanılmaz
    else:
        # 2) öngörülen konumun ±2 pikselindeki en parlak pikselden başlayan akı-ağırlıklı merkez
        ix, iy = int(round(x0)), int(round(y0))
        win = img[iy - 2: iy + 3, ix - 2: ix + 3]
        if np.isfinite(win).any():
            py, px = np.unravel_index(np.nanargmax(win), win.shape)
            c = align.centroid(img, ix - 2 + px, iy - 2 + py, half=2)
            if c is not None:
                cx, cy = c[0], c[1]
                out["method"] = "flux_weighted_centroid"
    if cx is not None:
        mra, mdec = (float(v[0]) for v in grid.all_pix2world([cx], [cy], 0))
        de, dn = _offsets_arcsec(mra, mdec, ra, dec)
        out.update(ra=round(mra, 6), dec=round(mdec, 6), offset_e_arcsec=round(de, 2), offset_n_arcsec=round(dn, 2))
    return out


def comparison_ensemble(analysis, seq: dict, exclude: list[tuple[float, float]], gmax: float = 16.0, min_snr: float = 30.0) -> dict:
    """Alandaki karşılaştırma yıldızlarıyla kare-kare sıfır noktası kararlılığı.

    Gaia DR3 yıldızları (G < gmax, hedeften > 25″ uzak, 25″ içinde benzer parlaklıkta komşusu olmayan) her
    karede ham piksellerden ölçülür. Her yıldızın akısı kendi ortancasına bölünür; bir karedeki oranların
    ortancası o karenin göreli ölçek katsayısı, MAD tabanlı saçılması ise sistematik belirsizliktir
    (PSF/açıklık kaybı ve kalibrasyon farklarını içerir).
    """
    from . import catalogs
    c = seq["meta"]["center"]
    radius = seq["meta"]["grid"]["nx"] * seq["meta"]["grid"]["pixscale_arcsec"] / 3600.0 / 2.0 * 0.85
    try:
        stars = analysis.pipeline.gaia(c["ra_deg"], c["dec_deg"], round(radius, 4))
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:120]}
    stars = [st for st in stars if st["g"] is not None]
    frames_raw = []
    for f in seq["frames"]:
        rec = analysis.db.get_raw(f["source_url"])
        frames_raw.append(read_spx(analysis.store.path_for(rec["sha256"])))
    table = []
    for st in stars:
        if st["g"] > gmax:
            continue
        if any(angular_separation_deg(st["ra"], st["dec"], r, d) * 3600.0 < 25.0 for r, d in exclude):
            continue
        if any(o is not st and o["g"] < st["g"] + 2.5 and angular_separation_deg(st["ra"], st["dec"], o["ra"], o["dec"]) * 3600.0 < 25.0 for o in stars):
            continue
        fl = []
        for f, frame in zip(seq["frames"], frames_raw):
            ra, dec = catalogs.propagate(st["ra"], st["dec"], st["pmra"], st["pmdec"], catalogs.GAIA_REF_EPOCH, f["epoch_jyear"])
            ph = aperture_photometry(frame, ra, dec)
            ok = ph["valid"] and ph["reliable"] and ph["err_mjy"] and ph["flux_mjy"] / ph["err_mjy"] >= min_snr
            fl.append(ph["flux_mjy"] if ok else np.nan)
        if np.isfinite(fl).sum() >= max(2, len(fl) - 1):
            table.append(fl)
    if len(table) < 3:
        return {"status": "too_few_comparison_stars", "n_stars": len(table)}
    arr = np.array(table)
    rel = arr / np.nanmedian(arr, axis=1, keepdims=True)
    scale = np.nanmedian(rel, axis=0)
    scatter = 1.4826 * np.nanmedian(np.abs(rel - scale), axis=0)
    return {"status": "ok", "n_stars": int(arr.shape[0]), "gmax": gmax,
            "frame_scale": [round(float(v), 4) for v in scale],
            "frame_scatter": [round(float(v), 4) for v in scatter],
            "systematic_frac": round(float(np.nanmedian(scatter)), 4),
            "method": "Gaia DR3 comparison stars, r=2 px aperture on native pixels, flux / own median"}


def wing_proxy(analysis, seq: dict, r_in: float = 5.0, r_out: float = 9.0, min_pixels: int = 30) -> dict:
    """Doymuş bir merkez kaynağın **doymamış** PSF kanatlarının parlaklığı (göreli gösterge).

    Merkezden r_in–r_out piksel halkasındaki geçerli ve şüpheli olmayan piksellerin ortancası. Nicel fotometri
    değildir: halka piksel kümesi kareden kareye değişir, PSF ve saçılmış ışık sürüme bağlıdır.
    """
    c = seq["meta"]["grid"]["nx"] // 2
    rows = []
    for f in seq["frames"]:
        fr = analysis._frame(seq, f["index"])
        img = fr["image"].astype(np.float64) - float(fr["background"])
        yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
        rr = np.hypot(xx - c, yy - c)
        sel = (rr >= r_in) & (rr <= r_out) & ~fr["invalid"] & ~fr["suspect"]
        v = img[sel]
        rows.append({"index": f["index"], "date": f["date_avg"], "n_pixels": int(v.size),
                     "wing_median_mjy_sr": None if v.size == 0 else round(float(np.median(v)), 3),
                     "usable": bool(v.size >= min_pixels)})
    use = [r for r in rows if r["usable"]]
    out = {"annulus_px": [r_in, r_out], "min_pixels": min_pixels, "frames": rows, "n_usable": len(use),
           "status": "indicative_only_not_photometry"}
    if len(use) >= 2:
        vals = [r["wing_median_mjy_sr"] for r in use]
        i_max, i_min = int(np.argmax(vals)), int(np.argmin(vals))
        out.update(max_over_min=round(vals[i_max] / vals[i_min], 2) if vals[i_min] > 0 else None,
                   date_min=use[i_min]["date"], date_max=use[i_max]["date"])
    return out


def blending(analysis, seq: dict, rows: list[dict], radius_arcsec: float = 20.0) -> dict:
    """Öngörülen hedef konumlarının çevresindeki katalog kaynakları (açıklık 12″, arka plan halkası 43″'ye uzanır).

    Gaia DR3 konumları kare dönemine özdevinimle ilerletilir; AllWISE konumları ≈2010.5 dönemindedir. Hedefin
    kendisi (öngörülen konuma 3″'den yakın Gaia kaynağı) listeden çıkarılır.
    """
    from . import catalogs
    c = seq["meta"]["center"]
    r = seq["meta"]["grid"]["nx"] * seq["meta"]["grid"]["pixscale_arcsec"] / 3600.0 / 2.0 * 1.45
    out = {"radius_arcsec": radius_arcsec, "gaia": [], "allwise": [], "status": "ok"}
    unavailable = {}
    try:
        gaia = analysis.pipeline.gaia(c["ra_deg"], c["dec_deg"], round(r, 4))
    except Exception as exc:
        gaia = []
        unavailable["gaia"] = str(exc)[:120]
    try:
        allwise = analysis.pipeline.allwise(c["ra_deg"], c["dec_deg"], round(r, 4))
    except Exception as exc:
        allwise = []
        unavailable["allwise"] = str(exc)[:120]
    if len(unavailable) == 2:
        return {"status": "unavailable", "reason": "; ".join(f"{name}: {reason}" for name, reason in unavailable.items()),
                "unavailable_catalogues": unavailable}
    if unavailable:
        out.update(status="partial", unavailable_catalogues=unavailable,
                   note="Only available catalogues were checked. Missing catalogue coverage does not establish an isolated source.")
    out["catalogue_provenance"] = {
        name: {"source_url": entries[0].get("source_url"), "epoch_jyear": entries[0].get("epoch_jyear"),
               **entries[0].get("provenance", {})}
        for name, entries in (("gaia", gaia), ("allwise", allwise)) if entries
    }
    for st in gaia:
        best = None
        for row, f in zip(rows, seq["frames"]):
            ra, dec = catalogs.propagate(st["ra"], st["dec"], st["pmra"], st["pmdec"], catalogs.GAIA_REF_EPOCH, f["epoch_jyear"])
            sep = angular_separation_deg(ra, dec, row["pred_ra"], row["pred_dec"]) * 3600.0
            if best is None or sep < best[0]:
                best = (sep, row["date"])
        if best and 3.0 <= best[0] <= radius_arcsec:
            out["gaia"].append({"id": st["id"], "g": st["g"], "min_sep_arcsec": round(best[0], 1), "date": best[1]})
        elif best and best[0] < 3.0:
            out["target_in_gaia"] = {"id": st["id"], "g": st["g"], "sep_arcsec": round(best[0], 2)}
    for w in allwise:
        best = min(((angular_separation_deg(w["ra"], w["dec"], row["pred_ra"], row["pred_dec"]) * 3600.0, row["date"]) for row in rows), default=None)
        if best and best[0] <= radius_arcsec:
            out["allwise"].append({"id": w["id"], "w1": w["w1"], "w2": w["w2"], "min_sep_arcsec": round(best[0], 1), "date": best[1]})
    out["gaia"].sort(key=lambda x: x["min_sep_arcsec"])
    out["allwise"].sort(key=lambda x: x["min_sep_arcsec"])
    out["n_within_aperture"] = sum(1 for x in out["gaia"] + out["allwise"] if x["min_sep_arcsec"] <= 12.3)
    return out


def measure_target(analysis, seq: dict, target: dict | None = None) -> dict:
    """Dizideki tüm karelerde hedefi ölçer ve dürüst durum basamaklarını üretir."""
    frames = seq["frames"]
    rows = []
    for f in frames:
        tp = f.get("target_predicted")
        ra, dec = (tp["ra"], tp["dec"]) if tp else (seq["meta"]["center"]["ra_deg"], seq["meta"]["center"]["dec_deg"])
        rows.append(measure_frame(analysis, seq, f["index"], ra, dec))
    located = [r for r in rows if r["ra"] is not None]
    saturated = [r for r in rows if r["method"] == "saturated_core_centroid" or (r["photometry"]["saturated"])]
    detected = [r for r in rows if r["method"] == "saturated_core_centroid" or (r["snr"] is not None and r["snr"] >= DETECT_SNR)]
    out = {"frames": rows, "n_frames": len(rows), "n_located": len(located), "n_detected": len(detected), "n_saturated": len(saturated),
           "detect_snr_threshold": DETECT_SNR, "status": {"data_available": len(rows) >= 2,
                                                         "source_detected": len(detected) >= max(2, math.ceil(0.5 * len(rows)))}}

    # ---- hareket: ölçülen konumlara zamanla doğrusal uyum (yay saniyesi/yıl), katalog özdevinimiyle karşılaştırma
    motion = None
    det_loc = [r for r in detected if r["ra"] is not None]
    if len(det_loc) >= 2 and det_loc[-1]["mjd"] - det_loc[0]["mjd"] > 30.0:
        ref = det_loc[0]
        t = np.array([(r["mjd"] - ref["mjd"]) / 365.25 for r in det_loc])
        e = np.array([_offsets_arcsec(r["ra"], r["dec"], ref["ra"], ref["dec"])[0] for r in det_loc])
        n = np.array([_offsets_arcsec(r["ra"], r["dec"], ref["ra"], ref["dec"])[1] for r in det_loc])
        pe = np.array([_offsets_arcsec(r["pred_ra"], r["pred_dec"], ref["pred_ra"], ref["pred_dec"])[0] for r in det_loc])
        pn = np.array([_offsets_arcsec(r["pred_ra"], r["pred_dec"], ref["pred_ra"], ref["pred_dec"])[1] for r in det_loc])
        al = seq["meta"].get("alignment", {})
        if all(r["method"] == "flux_weighted_centroid" for r in det_loc) and al.get("status") == "ok" and al.get("rms_arcsec"):
            # doymamış, yüksek S/N kaynak: aynı karelerde aynı yöntemle ölçülen Gaia yıldızlarının artığı (2B rms),
            # eksen başına hata olarak (temkinli) kullanılır; taban 0.1 piksel
            sig = max(float(al["rms_arcsec"]), CENTROID_FLOOR_PX * align.NATIVE_PIXSCALE_ARCSEC)
            sig_source = "sequence alignment rms vs Gaia (per-axis, floor 0.1 px)"
        else:
            sig = CENTROID_ERR_PX * align.NATIVE_PIXSCALE_ARCSEC
            sig_source = "assumed 0.3 px (saturated-core centroid)"
        sxx = float(np.sum((t - t.mean()) ** 2))
        mu_e = float(np.sum((t - t.mean()) * (e - e.mean())) / sxx)
        mu_n = float(np.sum((t - t.mean()) * (n - n.mean())) / sxx)
        mu_err = sig / math.sqrt(sxx)
        cat_e = float(np.sum((t - t.mean()) * (pe - pe.mean())) / sxx)
        cat_n = float(np.sum((t - t.mean()) * (pn - pn.mean())) / sxx)
        span = float(t[-1] - t[0])
        total = math.hypot(mu_e, mu_n)
        resid = math.hypot(mu_e - cat_e, mu_n - cat_n)
        motion = {
            "n_points": len(det_loc), "from_date": det_loc[0]["date"], "to_date": det_loc[-1]["date"], "span_years": round(span, 3),
            "fit_pm_e_arcsec_yr": round(mu_e, 2), "fit_pm_n_arcsec_yr": round(mu_n, 2), "fit_pm_total_arcsec_yr": round(total, 2),
            "fit_pm_err_arcsec_yr": round(mu_err, 2),
            "catalog_pm_e_arcsec_yr": round(cat_e, 2), "catalog_pm_n_arcsec_yr": round(cat_n, 2),
            "catalog_pm_total_arcsec_yr": round(math.hypot(cat_e, cat_n), 2),
            "measured_shift_arcsec": round(total * span, 2), "measured_shift_px": round(total * span / align.NATIVE_PIXSCALE_ARCSEC, 2),
            "predicted_shift_arcsec": round(math.hypot(cat_e, cat_n) * span, 2),
            "significance_sigma": round(total / (math.sqrt(2.0) * mu_err), 1),
            "residual_vs_catalog_sigma": round(resid / (math.sqrt(2.0) * mu_err), 1),
            "significant": bool(total > CHANGE_SIGMA * math.sqrt(2.0) * mu_err),
            "consistent_with_catalog": bool(resid <= 3.0 * math.sqrt(2.0) * mu_err),
            "per_point_error_arcsec": round(sig, 2), "per_point_error_source": sig_source,
            "methods": sorted({r["method"] for r in det_loc}),
            "note": "doğrusal uyum; paralaks ve gözlemci etkisi modellenmedi",
        }
    out["motion"] = motion

    # ---- parlaklık: yalnızca güvenilir (doymamış, geçerli) ve nicel toleranstaki noktalar; karşılaştırma
    #      yıldızı topluluğuyla kare ölçeği düzeltilir ve topluluk saçılması sistematik hata olarak eklenir
    good = [r for r in rows if r["photometry"]["valid"] and r["photometry"]["reliable"]]
    bright = None
    ens = None
    if len(good) >= 2:
        ens = comparison_ensemble(analysis, seq, [(r["pred_ra"], r["pred_dec"]) for r in rows[:1] + rows[-1:]])
        lam = np.array([r["photometry"]["lam_um"] for r in good])
        bw = float(np.median([r["photometry"]["bw_um"] for r in good]))
        ok = np.abs(lam - np.median(lam)) <= QUANT_TOL * bw
        tol_used = QUANT_TOL
        if ok.sum() < 2 or (len(good) >= 3 and ok.sum() < 3):
            # nicel toleransta yeterli nokta yok: dizinin görsel toleransındaki tüm noktalar kullanılır ve tayf eğimi
            # için temkinli bir sistematik eklenir (karşılaştırma yıldızları aynı dalga boyu kaymasını paylaşır)
            ok = np.ones(len(good), bool)
            tol_used = float(seq["meta"]["wavelength"]["tol"])
        use = [r for r, k in zip(good, ok) if k]
        if len(use) >= 2:
            fl = np.array([r["photometry"]["flux_mjy"] for r in use])
            er = np.array([r["photometry"]["err_mjy"] for r in use])
            sys_frac = 0.0
            normalized = False
            if ens and ens.get("status") == "ok":
                scale = np.array([ens["frame_scale"][r["index"]] for r in use])
                scat = np.array([ens["frame_scatter"][r["index"]] for r in use])
                if np.all(np.isfinite(scale)) and np.all(scale > 0):
                    fl = fl / scale
                    er = er / scale
                    sys_frac = float(np.nanmax(scat)) if np.isfinite(scat).any() else ens["systematic_frac"]
                    normalized = True
            if tol_used > QUANT_TOL:
                sys_frac = math.hypot(sys_frac, VISUAL_TOL_SYSTEMATIC)
            tot = np.sqrt(er ** 2 + (sys_frac * fl) ** 2)
            i_max, i_min = int(np.argmax(fl)), int(np.argmin(fl))
            diff = fl[i_max] - fl[i_min]
            sig = math.hypot(tot[i_max], tot[i_min])
            wmean = float(np.sum(fl / tot ** 2) / np.sum(1 / tot ** 2))
            chi2 = float(np.sum(((fl - wmean) / tot) ** 2))
            bright = {
                "n_points": len(use), "lam_um": round(float(np.median(lam[ok])), 5), "wavelength_tolerance_used": tol_used,
                "dlam_over_bw": [round(float((v - np.median(lam[ok])) / bw), 3) for v in lam[ok]],
                "normalized_by_comparison_stars": normalized, "systematic_frac": round(sys_frac, 4),
                "points": [{"date": r["date"], "flux_mjy": round(float(a), 3), "err_mjy": round(float(e), 3)} for r, a, e in zip(use, fl, tot)],
                "flux_min_mjy": round(float(fl[i_min]), 4), "flux_max_mjy": round(float(fl[i_max]), 4),
                "date_min": use[i_min]["date"], "date_max": use[i_max]["date"],
                "max_over_min": round(float(fl[i_max] / fl[i_min]), 3) if fl[i_min] > 0 else None,
                "diff_sigma": round(float(diff / sig), 1) if sig > 0 else None,
                "chi2_constant": round(chi2, 1), "dof": len(use) - 1,
                "caveats": ["aperture flux without aperture correction", "quick-release calibration",
                            f"wavelength offsets up to {tol_used} bandwidth" + ("; 10% systematic added for spectral slope" if tol_used > QUANT_TOL else ""),
                            "systematic error from comparison-star scatter" if normalized else "no comparison-star check: formal errors only"],
            }
    out["comparison"] = ens
    out["brightness"] = bright
    # WISE 0855 gibi tek karede eşik altı kaynaklar için: öngörülen konumlardaki zorlanmış fotometrinin ağırlıklı ortalaması
    forced = [r for r in rows if r["photometry"]["valid"] and r["photometry"]["err_mjy"]]
    if forced:
        fw = np.array([r["photometry"]["flux_mjy"] for r in forced])
        ew = np.array([r["photometry"]["err_mjy"] for r in forced])
        mean = float(np.sum(fw / ew ** 2) / np.sum(1 / ew ** 2))
        merr = float(1.0 / math.sqrt(np.sum(1 / ew ** 2)))
        out["forced_mean"] = {"n": len(forced), "flux_mjy": round(mean, 4), "err_mjy": round(merr, 4), "snr": round(mean / merr, 1),
                              "note": "öngörülen (yalnızca özdevinim) konumlarda zorlanmış açıklık fotometrisinin ağırlıklı ortalaması; bağımsız bir keşif ölçümü değildir"}
    else:
        out["forced_mean"] = None
    out["wing_proxy"] = wing_proxy(analysis, seq) if len(saturated) >= max(2, math.ceil(0.5 * len(rows))) else None
    # "Değişim görülüyor" ölçütü hareketle aynı eşiği kullanır (≥ 3σ); parlaklıkta ayrıca karşılaştırma yıldızı
    # denetimi ve en az %20 değişim aranır (PSF/açıklık kaybı farklarının altında kalan değişimler sayılmaz).
    bright_change = bool(bright and bright["normalized_by_comparison_stars"] and bright["diff_sigma"] and bright["diff_sigma"] >= CHANGE_SIGMA
                         and bright["max_over_min"] and bright["max_over_min"] >= MIN_BRIGHTNESS_RATIO)
    out["status"]["change_seen"] = bool((motion and motion["significant"]) or bright_change)
    out["status"]["change_kind"] = ("motion" if (motion and motion["significant"]) else ("brightness" if bright_change else None))
    out["blending"] = blending(analysis, seq, rows)
    out["status"]["change_scientifically_confirmed"] = False   # bu araç doğrulama iddia etmez
    return out


def separation_arcsec(a: dict, b: dict) -> float:
    return angular_separation_deg(a["ra"], a["dec"], b["ra"], b["dec"]) * 3600.0
