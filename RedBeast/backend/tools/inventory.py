"""Beş hedef için gerçek arşiv envanteri.

Kullanım:  python -m tools.inventory

Her hedef için IRSA TAP sorgusu gerçekten çalıştırılır. Çıktılar (proje kökünde):
- reports/inventory.json                 makine tarafından okunabilir özet
- reports/inventory/<id>_observations.csv  tekil gözlemlerin tam listesi
- reports/inventory.md                   kısa açıklamalı rapor
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
from pathlib import Path

from blinkspace import selection
from blinkspace.config import load_settings
from blinkspace.db import Database
from blinkspace.pipeline import Pipeline, mjd_to_iso
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.wavelength import WaveModel

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
TOL = 0.5
FOV = 6.0


def main() -> None:
    s = load_settings()
    db = Database(s.db_path)
    model = WaveModel.load(RESOURCES / "wave_model.json")
    pipe = Pipeline(s, db, model)
    (REPORTS / "inventory").mkdir(parents=True, exist_ok=True)
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "tolerance": TOL, "fov_arcmin": FOV, "time_standard": "UTC (MJD)", "targets": {}}
    md = ["# SPHEREx arşiv envanteri — beş hedef", "",
          f"Üretim: {out['generated_at']} · Servis: IRSA TAP (`spherex.plane ⨝ spherex.artifact`) · "
          f"Zaman standardı: UTC · Dalga boyu toleransı: {TOL}×Δλ · Alan: {FOV}′", ""]
    for tid, t in load_targets().items():
        ra, dec = t["search"]["ra_deg"], t["search"]["dec_deg"]
        kept, dropped, meta = pipe.observations(ra, dec)
        geo = pipe.geometry(FOV)
        cands, rejected = selection.build_candidates(kept, ra, dec, model, geo["min_edge_px"])
        groups = selection.find_groups(cands, TOL)
        by_det = collections.Counter(o.detector for o in kept)
        cand_by_det = collections.Counter(c.obs.detector for c in cands)
        lam_by_det = {}
        for d in sorted(cand_by_det):
            lams = [c.lam_um for c in cands if c.obs.detector == d]
            lam_by_det[str(d)] = [round(min(lams), 4), round(max(lams), 4)]
        visits = selection.split_visits(cands)
        rec = {
            "name": t["name"], "simbad_main_id": t["simbad_main_id"],
            "query_position": {"ra_deg": ra, "dec_deg": dec, "epoch_jyear": t["search"]["epoch_jyear"], "frame": "ICRS"},
            "adql": meta["adql"], "tap_url": meta["tap_url"], "tap_elapsed_s": meta.get("elapsed_s"),
            "n_rows": meta["rows"], "n_parsed": meta["parsed"], "n_unique": len(kept), "n_reprocessed_dropped": len(dropped),
            "by_detector": {str(k): v for k, v in sorted(by_det.items())},
            "by_collection": dict(collections.Counter(o.collection for o in kept)),
            "by_release": dict(collections.Counter(o.release for o in kept)),
            "by_pipeline_version": dict(collections.Counter(o.pipeline_version for o in kept)),
            "by_l2_tag_count": len({o.l2_tag for o in kept}),
            "mjd_first": min(o.mjd_start for o in kept) if kept else None,
            "mjd_last": max(o.mjd_start for o in kept) if kept else None,
            "date_first": mjd_to_iso(min(o.mjd_start for o in kept)) if kept else None,
            "date_last": mjd_to_iso(max(o.mjd_start for o in kept)) if kept else None,
            "n_usable_at_fov": len(cands),
            "n_rejected_near_edge": sum(1 for r in rejected if r["reason"] == "near_detector_edge"),
            "usable_by_detector": {str(k): v for k, v in sorted(cand_by_det.items())},
            "predicted_wavelength_range_by_detector_um": lam_by_det,
            "n_visits_any_wavelength": len(visits),
            "n_wavelength_groups": len(groups),
            "n_groups_with_2plus_visits": sum(1 for g in groups if len(g.visits) >= 2),
            "top_groups": [g.summary() for g in groups[:10]],
        }
        out["targets"][tid] = rec
        with (REPORTS / "inventory" / f"{tid}_observations.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["obs_id", "detector", "collection", "release", "l2_tag", "pipeline_version", "mjd_start_utc", "mjd_end_utc",
                        "date_start_utc", "exposure_s", "data_url", "checksum", "content_length", "usable_at_fov",
                        "pred_lam_um", "pred_bw_um", "edge_px", "footprint_icrs"])
            cmap = {c.obs.key: c for c in cands}
            for o in kept:
                c = cmap.get(o.key)
                w.writerow([o.obs_id, o.detector, o.collection, o.release, o.l2_tag, o.pipeline_version, o.mjd_start, o.mjd_end,
                            mjd_to_iso(o.mjd_start), o.exposure_s, s.irsa_base + o.uri, o.checksum, o.content_length,
                            int(c is not None), "" if c is None else round(c.lam_um, 5), "" if c is None else round(c.bw_um, 5),
                            "" if c is None else round(c.edge_px, 1),
                            " ".join(f"{a:.5f},{b:.5f}" for a, b in o.footprint)])
        md += [f"## {t['name']} (`{tid}`)", "",
               f"- Kimlik: `{t['simbad_main_id']}` · sorgu konumu ICRS ({ra:.5f}, {dec:.5f}), dönem J{t['search']['epoch_jyear']}",
               f"- Arşiv satırı: {rec['n_rows']} · tekil gözlem×dedektör: {rec['n_unique']} · elenen yeniden işleme kopyası: {rec['n_reprocessed_dropped']}",
               f"- Zaman aralığı (UTC): {rec['date_first']} → {rec['date_last']}",
               f"- Dedektör başına: {rec['by_detector']}",
               f"- Koleksiyon: {rec['by_collection']} · işleme sürümü: {rec['by_pipeline_version']}",
               f"- {FOV}′ alan için kullanılabilir (kenardan uzak): {rec['n_usable_at_fov']} · kenar nedeniyle elenen: {rec['n_rejected_near_edge']}",
               f"- Öngörülen dalga boyu aralığı (µm): {rec['predicted_wavelength_range_by_detector_um']}",
               f"- Dalga boyu grubu: {rec['n_wavelength_groups']} · en az iki ziyaretli grup: {rec['n_groups_with_2plus_visits']}", ""]
        if groups:
            md += ["| λ ref (µm) | Δλ (µm) | kare | ziyaret | aralık (gün) | dedektör |", "|---|---|---|---|---|---|"]
            for g in groups[:6]:
                sm = g.summary()
                md.append(f"| {sm['lam_ref_um']} | {sm['bw_ref_um']} | {sm['n_frames']} | {sm['n_visits']} | {sm['span_days']} | {sm['detectors']} |")
            md.append("")
        md += [f"Tam liste: `reports/inventory/{tid}_observations.csv`", ""]
        print(f"{t['name']}: {rec['n_unique']} tekil, {rec['n_usable_at_fov']} kullanılabilir, "
              f"{rec['n_groups_with_2plus_visits']} grup ≥2 ziyaret; en iyi: {groups[0].summary() if groups else None}")
    (REPORTS / "inventory.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    (REPORTS / "inventory.md").write_text("\n".join(md), encoding="utf-8")
    print("yazıldı:", REPORTS / "inventory.json")


if __name__ == "__main__":
    main()
