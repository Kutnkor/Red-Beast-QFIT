"""Beş hedefin bilimsel raporunu gerçek dizilerden üretir.

Kullanım:  python -m tools.target_report

Çıktılar (proje kökünde):
- reports/targets/<id>.json   ölçümlerin tamamı (makine tarafından okunabilir)
- reports/targets/<id>.md     İngilizce rapor
- reports/targets/<id>.png    karelerin kontrol görseli (büyütülmüş önizlemeler; ölçüm için değildir)
- reports/targets/README.md   özet tablo (İngilizce) · reports/targets/OZET.md (Türkçe)

Durum basamakları ayrı tutulur: data available → source detected → change seen → scientifically confirmed.
Son basamak bu araçla hiçbir zaman "evet" olmaz.
"""
from __future__ import annotations

import datetime as dt
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from blinkspace.analysis import Analysis
from blinkspace.config import PIPELINE_VERSION, load_settings
from blinkspace.db import Database
from blinkspace.measure import measure_target
from blinkspace.pipeline import Pipeline
from blinkspace.spectrum import load_spectrum
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.tracks import load_track
from blinkspace.wavelength import WaveModel

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "targets"

ALTERNATIVES = {
    "barnard": [
        "Where the method is saturated_core_centroid, the location describes the invalid saturated core rather than the stellar flux; pixel phase and bloom can shift that centroid.",
    ],
    "eps-indi-b": [
        "Ba and Bb are unresolved at SPHEREx's pixel scale. A measured location or flux refers to their combined image, not a resolved component.",
    ],
    "wise-0855": [
        "Flux at a predicted position can include unrelated background sources. The current catalogue blending check and per-frame S/N, when available, must be inspected before attributing the flux to WISE 0855.",
        "A co-moving display stack is available at the sequence track_stack endpoint. It aligns catalogue predictions but does not automatically remove blending or constitute a detection; quantitative values remain native-pixel forced photometry.",
    ],
    "rw-aur": [
        "A and B are unresolved at SPHEREx's pixel scale; any supported change refers to their combined light.",
        "Aperture losses can differ with PSF and wavelength. Comparison-star normalisation and the explicitly reported systematic error only partly control these effects; no extinction mechanism is inferred from this report.",
    ],
    "r-dra": [
        "Saturated or invalid core pixels have no flux measurement. A wing-brightness proxy, if available, is only indicative and is not used to establish variability.",
        "Bloom, halo, persistence and scattered light can affect centroids and background estimates; the actual per-frame quality flags above identify which effects were recorded.",
    ],
}


def alternative_explanations(tid, target, sequence, measurement):
    notes = list(ALTERNATIVES[tid])
    parallax = target.get("parallax_mas")
    if parallax is not None:
        notes.append(f"Observer parallax and spacecraft position are not modelled. The catalogue parallax is {parallax / 1000:.4f} arcsec ({parallax / 1000 / 6.15:.3f} SPHEREx pixels).")
    motion = measurement.get("motion")
    if motion:
        notes.append(f"The current motion fit uses per-point error {motion['per_point_error_arcsec']} arcsec: {motion['per_point_error_source']}.")
    notes.append(f"In this sequence, {measurement['n_detected']}/{measurement['n_frames']} frames meet the source-detection rule; {measurement['n_saturated']} frames are flagged as saturated at the target.")
    brightness = measurement.get("brightness")
    if brightness:
        notes.append(f"The current brightness analysis uses wavelength tolerance {brightness['wavelength_tolerance_used']} bandwidth and a {100 * brightness['systematic_frac']:.1f}% systematic term. These values are computed for this sequence, not inherited from earlier reports.")
    if not measurement.get("comparison") or measurement["comparison"].get("status") != "ok":
        notes.append("A valid comparison-star ensemble is unavailable for this measurement; no ensemble-verified brightness change is claimed.")
    notes.append("The scientific-confirmation status remains false. Neither catalogue predictions nor the display stack provide independent confirmation.")
    return notes


def yes(v) -> str:
    return "yes" if v else "no"


def contact_sheet(s, seq: dict, path: Path, scale: int = 5) -> None:
    tiles = []
    for f in seq["frames"]:
        im = Image.open(s.processed_dir / seq["id"] / f["png"]).convert("LA")
        bg = Image.new("RGB", im.size, (70, 20, 70))        # ölçüm yok: mor zemin
        bg.paste(im.convert("RGB"), mask=im.split()[1])
        bg = bg.resize((im.width * scale, im.height * scale), Image.NEAREST)
        d = ImageDraw.Draw(bg)
        d.rectangle([0, 0, bg.width, 13], fill=(0, 0, 0))
        d.text((3, 1), f"{f['date_avg'][:10]}  {f['lam_um']:.3f} um  D{f['detector']} {f['release']}", fill=(255, 220, 90))
        tiles.append(bg)
    cols = min(4, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    w, h = tiles[0].size
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 4, rows * h + (rows - 1) * 4), (20, 20, 20))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * (w + 4), (i // cols) * (h + 4)))
    sheet.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Recompute native measurements even when fingerprint-matched precomputed measurements exist")
    args = parser.parse_args()
    s = load_settings()
    db = Database(s.db_path)
    targets = load_targets()
    pipe = Pipeline(s, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    an = Analysis(s, db, pipe)
    OUT.mkdir(parents=True, exist_ok=True)
    inv = json.loads((ROOT / "reports" / "inventory.json").read_text(encoding="utf-8"))["targets"]
    presets = db.get_meta("preset_sequences", {})
    spectra = db.get_meta("preset_spectra", {})
    wise_auto = db.get_meta("wise0855_auto_wavelength_check")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summary = []
    for tid, t in targets.items():
        seq = db.get_sequence(presets[tid])
        cached = load_track(s.processed_dir, seq)
        measurement_path = s.processed_dir / seq["id"] / "target_measurement.json"
        if not args.refresh and cached["source"] == "precomputed" and measurement_path.exists():
            m = json.loads(measurement_path.read_text(encoding="utf-8"))
        else:
            m = measure_target(an, seq, t)
        meta, frames, iv = seq["meta"], seq["frames"], inv[tid]
        alternatives = alternative_explanations(tid, t, seq, m)
        releases = ", ".join(sorted({f["release"].upper() for f in frames}))
        st = m["status"]
        sp = [load_spectrum(s, x["result_id"]) for x in spectra.get(tid, [])]
        rec = {"target": t, "inventory": iv, "inventory_note": "Bundled archive inventory snapshot; current sequence discovery provenance is in meta.archive.", "sequence_id": seq["id"], "pipeline_version": meta["pipeline_version"], "generated_at": now,
               "params": seq["params"], "meta": meta, "frames": frames, "measurement": m,
               "spectra": [{k: x[k] for k in ("id", "date_window", "n_points", "n_reliable", "span_days")} for x in sp if x],
               "alternatives": alternatives}
        if tid == "wise-0855":
            rec["auto_wavelength_check"] = wise_auto
        (OUT / f"{tid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        contact_sheet(s, seq, OUT / f"{tid}.png")

        al = meta["alignment"]
        w = meta["wavelength"]
        L = [f"# {t['name']} — target report", "",
             f"Generated {now} · BlinkSpace pipeline {meta['pipeline_version']} · sequence `{seq['id']}` · data: SPHEREx {releases} Level-2 spectral images (IRSA).", "",
             "## Status", "",
             "| Step | Result |", "|---|---|",
             f"| Data available (≥ 2 matched-wavelength frames) | **{yes(st['data_available'])}** — {meta['n_frames']} frames, {meta['n_visits']} visits, {meta['span_days']:.0f} days |",
             f"| Source detected at the expected position | **{yes(st['source_detected'])}** — {m['n_detected']}/{m['n_frames']} frames ({m['n_saturated']} saturated) |",
             f"| Change seen | **{yes(st['change_seen'])}**" + (f" — {st['change_kind']}" if st["change_kind"] else "") + " |",
             "| Change scientifically confirmed | **no** — this tool never claims confirmation |", "",
             "## 1. Identity and coordinate source", "",
             f"- SIMBAD main id: `{t['simbad_main_id']}` · type {t['object_type']} · spectral type {t['spectral_type']}",
             f"- Aliases: {', '.join(t['aliases'][:6])}",
             f"- Catalogue position (ICRS, epoch J{t['epoch_jyear']}): {t['ra_hms']} {t['dec_dms']} = ({t['ra_deg']:.6f}, {t['dec_deg']:.6f}) · source {t['coo_bibcode']}",
             f"- Proper motion: ({t['pmra_masyr']}, {t['pmdec_masyr']}) mas/yr · source {t['pm_bibcode']} · parallax {t['parallax_mas']} mas",
             f"- {t['notes']['en']}"]
        if "primary_star" in t:
            L.append(f"- Not the primary: `{t['primary_star']['simbad_main_id']}` is {t['primary_star']['separation_arcsec']}″ away.")
        if "reference_coords" in t:
            c = t["reference_coords"]
            L.append(f"- Reference (WISE-epoch) coordinate {c['ra']} {c['dec']} is {c['offset_from_j2000_arcsec']}″ from the J2000 position (≈ WISE epoch) and {c['offset_from_search_center_arcsec']}″ from the J2026.0 search centre.")
        L += ["", "## 2. Query parameters", "",
              f"- Search centre (ICRS): ({seq['params']['ra_deg']}, {seq['params']['dec_deg']}), epoch J{t['search']['epoch_jyear']} — {t['search']['shift_arcsec']}″ from the J2000 position by proper motion only (no parallax, no observer position).",
              f"- Field {seq['params']['fov_arcmin']}′ · wavelength tolerance {seq['params']['tol']} × bandwidth · max frames {seq['params']['max_frames']} · requested wavelength: {seq['params']['lam_um'] or 'automatic (best time coverage)'}",
              f"- Discovery service: {meta['archive']['service']}; cached index: {meta['archive']['from_cache']}."]
        if meta['archive'].get('adql'):
            L.append(f"- ADQL: `{meta['archive']['adql']}`")
        for request in meta['archive'].get('sia_requests', []):
            L.append(f"- SIA query: {request['url']} · response SHA-256 `{request['response_sha256']}`")
        if t.get("preferred_lam_rationale"):
            L.append(f"- Preset wavelength rationale from the prior inventory: {t['preferred_lam_rationale']['en']}")
        L += ["", "## 3. Bundled inventory snapshot", "",
              "This inventory was supplied with the project; it is not represented as a fresh search. Current sequence discovery provenance appears in the JSON report under meta.archive.", "",
              f"- Archive rows {iv['n_rows']} · unique observation×detector {iv['n_unique']} · reprocessed copies dropped {iv['n_reprocessed_dropped']}",
              f"- Time range (UTC): {iv['date_first']} → {iv['date_last']} · per detector {iv['by_detector']}",
              f"- Collections {iv['by_collection']} · pipeline versions {iv['by_pipeline_version']}",
              f"- Usable at this field size {iv['n_usable_at_fov']} (rejected near detector edge: {iv['n_rejected_near_edge']}) · wavelength groups with ≥ 2 visits: {iv['n_groups_with_2plus_visits']}",
              f"- Full list: `reports/inventory/{tid}_observations.csv`", "",
              "## 4. Selected images", "",
              "| # | Date (UTC) | Obs. id | Det. | Release / L2 tag | Pipeline | λ (µm) | Δλ/bw | invalid | suspect | comparable | raw SHA-256 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for f in frames:
            L.append(f"| {f['index'] + 1} | {f['date_avg']} | {f['obs_id']} | {f['detector']} | {f['release']} / {f['l2_tag']} | {f['pipeline_version']} | "
                     f"{f['lam_um']} | {f['dlam_over_bw']:+.2f} | {f['invalid_frac']:.3f} | {f['suspect_frac']:.3f} | {f['comparable_frac']:.3f} | `{f['raw_sha256'][:16]}…` |")
        L += ["", f"![frames]({tid}.png)", "", "*Preview tiles (magnified, common display scale; purple = no measurement). Previews are for inspection only, not for measurement.*", "",
              "## 5. Time span and wavelength agreement", "",
              f"- {meta['n_frames']} frames in {meta['n_visits']} visits over {meta['span_days']:.1f} days ({frames[0]['date_avg'][:10]} → {frames[-1]['date_avg'][:10]}).",
              f"- Reference wavelength {w['lam_ref_um']} µm, bandwidth {w['bw_ref_um']} µm (FWHM); all frames within {w['tol']} × bandwidth at the field centre "
              f"(largest offset {max(abs(f['dlam_over_bw']) for f in frames):.2f}). The matched group in the archive has {w['group_n_frames']} frames in {w['group_n_visits']} visits.",
              f"- Pixels whose wavelength is outside the tolerance are masked per frame; area comparable in all frames: {100 * meta['common_comparable_frac']:.0f}%.", "",
              "## 6. Quality issues and rejected images", ""]
        rej = meta["selection"]["rejected_after_download"]
        L.append("- Rejected after download: " + ("none" if not rej else "; ".join(f"{r['obs_id']} D{r['detector']} ({r['reason']})" for r in rej)))
        L.append(f"- Warnings: {', '.join(meta['warnings']) or 'none'}")
        for f in frames:
            fl = f["quality"]["target"]["flags"]
            L.append(f"- Frame {f['index'] + 1}: flags within 2.5 px of field centre: {', '.join(f'{k} ({v})' for k, v in fl.items()) or 'none'}; L2 QA {f['quality']['l2_dqa']}; PSF FWHM {f['psf_fwhm_arcsec']:.2f}″ ({f['psf_kind']}).")
        L += ["", "## 7. Alignment check", ""]
        if al.get("status") == "ok":
            L.append(f"- {al['n_measurements']} centroid measurements of Gaia DR3 stars (G ≤ {al['gmax']}) propagated to each frame epoch: median offset "
                     f"({al['median_de_arcsec']}″ E, {al['median_dn_arcsec']}″ N), rms {al['rms_arcsec']}″ = {al['rms_arcsec'] / 6.15:.2f} pixel.")
            L.append("- Per frame: " + "; ".join(f"#{p['index'] + 1}: n={p['n_stars']}" + (f", rms {p['rms_arcsec']}″" if p.get("rms_arcsec") is not None else "") for p in al["per_frame"]))
        else:
            L.append(f"- Not available: {al.get('status')} {al.get('reason', '')}")
        L += ["", "## 8. Detectability of the source", "",
              "| # | Date | Method | Offset from prediction (E, N ″) | Aperture flux (mJy) | S/N | Note |", "|---|---|---|---|---|---|---|"]
        for r in m["frames"]:
            ph = r["photometry"]
            flux = "no measurement" if ph["flux_mjy"] is None else f"{ph['flux_mjy']:.3f} ± {ph['err_mjy']:.3f}"
            off = "—" if r["offset_e_arcsec"] is None else f"{r['offset_e_arcsec']:+.2f}, {r['offset_n_arcsec']:+.2f}"
            L.append(f"| {r['index'] + 1} | {r['date'][:10]} | {r['method'] or 'not located'} | {off} | {flux} | {r['snr'] if r['snr'] is not None else '—'} | {ph['reason'] or ''} |")
        if m.get("forced_mean"):
            fm = m["forced_mean"]
            L += ["", f"- Weighted mean of forced photometry at the predicted positions: {fm['flux_mjy']} ± {fm['err_mjy']} mJy (S/N {fm['snr']}, {fm['n']} frames). This is a mean at a known position, not an independent detection."]
        bl = m.get("blending") or {}
        if bl.get("status") in ("ok", "partial"):
            near = [f"Gaia DR3 {x['id']} (G={x['g']:.1f}, {x['min_sep_arcsec']}″ on {x['date'][:10]})" for x in bl["gaia"][:3]] + \
                   [f"AllWISE {x['id']} (W1={x['w1']}, W2={x['w2']}, {x['min_sep_arcsec']}″, epoch ≈2010.5)" for x in bl["allwise"][:3]]
            L += ["", f"**Blending.** Catalogue sources within {bl['radius_arcsec']:.0f}″ of the predicted positions (aperture radius 12.3″): " + ("; ".join(near) if near else "none") + "."]
            if bl.get("status") == "partial":
                L.append(f"Only available catalogues are included. Unavailable: {', '.join(bl['unavailable_catalogues'])}. An empty list is not evidence that the aperture is isolated.")
        elif bl:
            L += ["", f"**Blending check unavailable.** {bl.get('reason', bl.get('status'))}. Absence of this check is not evidence that the aperture is isolated."]
        if tid == "wise-0855" and wise_auto:
            L.append(f"- Control at {wise_auto['lam_um']} µm (the automatically chosen group, sequence `{wise_auto['sequence_id']}`): forced mean {wise_auto['flux_mjy']} ± {wise_auto['err_mjy']} mJy "
                     f"(S/N {wise_auto['snr']}). Flux at a wavelength where the brown dwarf should be undetectable shows that the aperture is contaminated by the background source.")
        L += ["", "## 9. Possible change seen", ""]
        mo, b = m["motion"], m["brightness"]
        if mo:
            L.append(f"- **Motion.** Linear fit to {mo['n_points']} positions over {mo['span_years']} yr: ({mo['fit_pm_e_arcsec_yr']:+.2f}, {mo['fit_pm_n_arcsec_yr']:+.2f}) ± {mo['fit_pm_err_arcsec_yr']} ″/yr (E, N); "
                     f"catalogue ({mo['catalog_pm_e_arcsec_yr']:+.2f}, {mo['catalog_pm_n_arcsec_yr']:+.2f}) ″/yr. Total shift {mo['measured_shift_arcsec']}″ = {mo['measured_shift_px']} pixels; "
                     f"significance {mo['significance_sigma']}σ; deviation from catalogue {mo['residual_vs_catalog_sigma']}σ. Per-point error {mo['per_point_error_arcsec']}″ ({mo['per_point_error_source']}).")
        else:
            L.append("- **Motion.** Not measurable (fewer than two located detections more than 30 days apart).")
        if b:
            pts = ", ".join(f"{p['date'][:10]}: {p['flux_mjy']:.1f} ± {p['err_mjy']:.1f}" for p in b["points"])
            L.append(f"- **Brightness.** {b['n_points']} reliable points at {b['lam_um']} µm (mJy; {'normalised by ' + str(m['comparison']['n_stars']) + ' comparison stars' if b['normalized_by_comparison_stars'] else 'no comparison-star check'}; "
                     f"systematic {100 * b['systematic_frac']:.0f}%; wavelength tolerance used {b['wavelength_tolerance_used']}): {pts}. Max/min {b['max_over_min']}, difference {b['diff_sigma']}σ.")
        else:
            L.append("- **Brightness.** Insufficient reliable matched-wavelength measurements for a brightness comparison; consult the per-frame measurement reasons above.")
        if m.get("wing_proxy"):
            wp = m["wing_proxy"]
            L.append(f"- Wing-brightness proxy (unsaturated pixels 5–9 px from the centre, indicative only): max/min {wp.get('max_over_min')} over {wp['n_usable']} usable frames. Not used for the status above.")
        for x in sp:
            if x:
                rel = [p for p in x["points"] if p["valid"] and p.get("reliable")]
                L.append(f"- Spectrum `{x['id'][:12]}…` window {x['date_window'][0][:10]} → {x['date_window'][1][:10]}: {x['n_points']} points, {len(rel)} reliable"
                         + (": " + ", ".join(f"{p['lam_um']:.3f} µm {p['flux_mjy']:.0f}" for p in rel[:10]) + " mJy" if rel else "") + ". Points are not simultaneous.")
        L += ["", "## 10. Uncertainties and alternative explanations", ""] + [f"- {x}" for x in alternatives]
        L += ["", "## 11. How to reproduce", "", "```bash", "cd backend",
              f"python -m tools.run_search --target {tid}        # query, select, download, align, preview",
              f"python -m tools.measure_presets --only {tid}     # detection, motion, brightness",
              "python -m tools.target_report                  # regenerate these reports", "```", "",
              f"Raw cutouts are stored unmodified under `data/raw/<sha256>.fits`; the SHA-256 of each is in the table above and in `{tid}.json`. "
              "A later archive update produces a new sequence id; this report refers to the sequence above.", ""]
        (OUT / f"{tid}.md").write_text("\n".join(L), encoding="utf-8")
        summary.append({"id": tid, "name": t["name"], "seq": seq["id"], "lam": w["lam_ref_um"], "frames": meta["n_frames"], "visits": meta["n_visits"],
                        "span": meta["span_days"], "st": st, "det": f"{m['n_detected']}/{m['n_frames']}", "sat": m["n_saturated"],
                        "motion": mo, "bright": b, "al": al.get("rms_arcsec")})
        print(f"{tid}: {st}")

    def change(x, tr=False):
        if x["st"]["change_kind"] == "motion":
            mo = x["motion"]
            consistency = ("katalogla uyumlu" if mo['consistent_with_catalog'] else "katalogla uyumsuz") if tr else ("consistent with catalogue" if mo['consistent_with_catalog'] else "inconsistent with catalogue")
            return (f"hareket: {mo['measured_shift_px']} piksel, {mo['significance_sigma']}σ, {consistency}" if tr else
                    f"motion: {mo['measured_shift_px']} px, {mo['significance_sigma']}σ, {consistency}")
        if x["st"]["change_kind"] == "brightness":
            b = x["bright"]
            return (f"parlaklık: {b['max_over_min']}×, {b['diff_sigma']}σ" if tr else f"brightness: {b['max_over_min']}×, {b['diff_sigma']}σ")
        return "—"

    en = ["# Five-target test summary", "", f"Generated {now} · pipeline {PIPELINE_VERSION} · real SPHEREx data only (no synthetic data in this table).", "",
          "| Target | λ (µm) | Frames / visits / days | Data available | Source detected | Change seen | Scientifically confirmed | Alignment rms (″) |", "|---|---|---|---|---|---|---|---|"]
    trl = ["# Beş hedef test özeti", "", f"Üretim: {now} · işlem sürümü {PIPELINE_VERSION} · yalnızca gerçek SPHEREx verisi.", "",
           "| Hedef | λ (µm) | Kare / ziyaret / gün | Veri mevcut | Kaynak seçiliyor | Değişim görülüyor | Bilimsel olarak doğrulandı | Hizalama rms (″) |", "|---|---|---|---|---|---|---|---|"]
    for x in summary:
        en.append(f"| [{x['name']}]({x['id']}.md) | {x['lam']} | {x['frames']} / {x['visits']} / {x['span']:.0f} | {yes(x['st']['data_available'])} | "
                  f"{yes(x['st']['source_detected'])} ({x['det']}, {x['sat']} saturated) | {yes(x['st']['change_seen'])} {change(x)} | no | {x['al']} |")
        trl.append(f"| [{x['name']}]({x['id']}.md) | {x['lam']} | {x['frames']} / {x['visits']} / {x['span']:.0f} | {'evet' if x['st']['data_available'] else 'hayır'} | "
                   f"{'evet' if x['st']['source_detected'] else 'hayır'} ({x['det']}, {x['sat']} doymuş) | {'evet' if x['st']['change_seen'] else 'hayır'} {change(x, True)} | hayır | {x['al']} |")
    en += ["", "\"Change seen\" means ≥ 3σ in this tool's own measurement (motion: linear fit to measured positions; brightness: aperture photometry on native pixels, "
           "normalised by comparison stars, ≥ 20% change). It is not a scientific confirmation. Absence of a result is reported as such.", ""]
    trl += ["", "\"Değişim görülüyor\": bu aracın kendi ölçümünde ≥ 3σ (hareket: ölçülen konumlara doğrusal uyum; parlaklık: ham piksellerde açıklık fotometrisi, "
            "karşılaştırma yıldızlarıyla ölçeklenmiş, en az %20 değişim). Bilimsel doğrulama değildir. Sonuç yokluğu olduğu gibi raporlanır.", ""]
    (OUT / "README.md").write_text("\n".join(en), encoding="utf-8")
    (OUT / "OZET.md").write_text("\n".join(trl), encoding="utf-8")
    print("yazıldı:", OUT)


if __name__ == "__main__":
    main()
