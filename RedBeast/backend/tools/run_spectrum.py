"""Komut satırından spektrum üretir (sunucu olmadan).

Kullanım:
  python -m tools.run_spectrum --target rw-aur --date 2025-09-03 --window 10 --points 16
  python -m tools.run_spectrum --ra 150.1 --dec 2.2
"""
from __future__ import annotations

import argparse
import time

from blinkspace.api import parse_date
from blinkspace.config import load_settings
from blinkspace.coords import parse_position
from blinkspace.db import Database
from blinkspace.pipeline import InsufficientData, Pipeline
from blinkspace.spectrum import SpectrumParams, load_spectrum, run_spectrum
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.wavelength import WaveModel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target")
    ap.add_argument("--ra")
    ap.add_argument("--dec")
    ap.add_argument("--date")
    ap.add_argument("--window", type=float, default=14.0)
    ap.add_argument("--points", type=int, default=24)
    ap.add_argument("--lam-min", type=float)
    ap.add_argument("--lam-max", type=float)
    a = ap.parse_args()
    s = load_settings()
    db = Database(s.db_path)
    targets = load_targets()
    pipe = Pipeline(s, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    if a.target:
        t = targets[a.target]
        ra, dec = t["search"]["ra_deg"], t["search"]["dec_deg"]
    else:
        pos = parse_position(a.ra, a.dec)
        ra, dec = pos.ra_deg, pos.dec_deg
    params = SpectrumParams(ra, dec, parse_date(a.date), a.window, a.points, a.target, a.lam_min, a.lam_max)
    t0 = time.time()
    try:
        res = run_spectrum(pipe, params)
    except InsufficientData as exc:
        print("YETERSİZ VERİ:", exc.reason, exc.detail)
        return
    sp = load_spectrum(s, res["result_id"])
    print(f"{res} {time.time() - t0:.1f} s | pencere {sp['date_window']} | pencere içi pozlama {sp['n_exposures_in_window']} | "
          f"nokta {sp['n_points']} güvenilir {sp['n_reliable']} | {sp['span_days']} gün")
    for p in sp["points"]:
        flux = "—" if p.get("flux_mjy") is None else f"{p['flux_mjy']:9.2f} ± {p['err_mjy']:.2f}"
        print(f"  λ={p.get('lam_um')} D{p['detector']} {p['date'][:16]} {flux} mJy "
              f"{'güvenilir' if p.get('reliable') else (p.get('reason') or 'güvenilmez')} {list((p.get('flags') or {}).keys())}")


if __name__ == "__main__":
    main()
