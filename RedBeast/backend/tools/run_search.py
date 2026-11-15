"""Komut satırından tek bir hazırlama işi çalıştırır (sunucu olmadan).

Kullanım:
  python -m tools.run_search --target barnard
  python -m tools.run_search --ra 150.1 --dec 2.2 --fov 6 --frames 8 [--lam 1.5]
"""
from __future__ import annotations

import argparse
import json
import time

from blinkspace.config import load_settings
from blinkspace.coords import parse_position
from blinkspace.db import Database
from blinkspace.pipeline import InsufficientData, Pipeline, SearchParams
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.wavelength import WaveModel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target")
    ap.add_argument("--ra")
    ap.add_argument("--dec")
    ap.add_argument("--ra-unit", default="auto")
    ap.add_argument("--fov", type=float, default=6.0)
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--lam", type=float)
    ap.add_argument("--tol", type=float, default=0.5)
    a = ap.parse_args()
    s = load_settings()
    db = Database(s.db_path)
    targets = load_targets()
    pipe = Pipeline(s, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    if a.target:
        t = targets[a.target]
        ra, dec = t["search"]["ra_deg"], t["search"]["dec_deg"]
        lam = a.lam if a.lam is not None else t.get("preferred_lam_um")
    else:
        p = parse_position(a.ra, a.dec, a.ra_unit)
        ra, dec, lam = p.ra_deg, p.dec_deg, a.lam
    params = SearchParams(ra, dec, a.fov, lam, a.tol, a.frames, None, None, a.target)
    t0 = time.time()

    def report(stage, progress, detail=None):
        print(f"  [{time.time() - t0:6.1f}s] {stage:12s} {progress:4.0%} {detail or ''}")

    try:
        res = pipe.run(params, report)
    except InsufficientData as exc:
        print("YETERSİZ VERİ:", exc.reason, json.dumps(exc.detail, indent=1)[:1500])
        return
    print("sonuç:", res, f"toplam {time.time() - t0:.1f} s")
    seq = db.get_sequence(res["sequence_id"])
    m = seq["meta"]
    print(json.dumps({k: m[k] for k in ("id", "status", "n_frames", "n_visits", "span_days", "wavelength", "display", "warnings",
                                         "common_valid_frac", "common_comparable_frac", "timings")}, indent=1, default=str)[:2500])
    print("hizalama:", json.dumps({k: v for k, v in m["alignment"].items() if k != "per_frame"}))
    print("elenenler:", m["selection"]["rejected_after_download"])
    for f in seq["frames"]:
        q = f["quality"]["target"]
        print(f"  #{f['index']} {f['date_avg']} {f['obs_id']} D{f['detector']} {f['release']} v{f['pipeline_version']} "
              f"λ={f['lam_um']} Δλ/bw={f['dlam_over_bw']:+.2f} bkg={f['background']['value_mjy_sr']} σ={f['background']['sigma_mjy_sr']} "
              f"geçersiz={f['invalid_frac']} şüpheli={f['suspect_frac']} uyumlu={f['comparable_frac']} hedef bayrak={q['flags']} doymuş={q['saturated']}")
    print("klasör:", s.processed_dir / res["sequence_id"])


if __name__ == "__main__":
    main()
