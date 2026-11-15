"""Hazır hedefler için örnek spektrumları üretir ve kimliklerini `meta.preset_spectra` kaydına yazar.

Kullanım:  python -m tools.preset_spectra

RW Aurigae: 0.73–1.7 µm (doymamış bölgeyi içerir), üç dönem. Eps Indi B: tüm dalga boyları, en yoğun pencere.
"""
from __future__ import annotations

import json

from blinkspace.api import parse_date
from blinkspace.config import load_settings
from blinkspace.db import Database
from blinkspace.pipeline import InsufficientData, Pipeline
from blinkspace.spectrum import SpectrumParams, load_spectrum, run_spectrum
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.wavelength import WaveModel

PLAN = {
    "rw-aur": [("2025-09-03", 12.0, 18, 0.73, 1.7), ("2026-03-08", 12.0, 18, 0.73, 1.7), ("2026-09-08", 12.0, 18, 0.73, 1.7)],
    "eps-indi-b": [(None, 14.0, 30, None, None)],
}


def main() -> None:
    s = load_settings()
    db = Database(s.db_path)
    targets = load_targets()
    pipe = Pipeline(s, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    out = {}
    for tid, runs in PLAN.items():
        t = targets[tid]
        out[tid] = []
        for date, window, points, lmin, lmax in runs:
            params = SpectrumParams(t["search"]["ra_deg"], t["search"]["dec_deg"], parse_date(date), window, points, tid, lmin, lmax)
            try:
                res = run_spectrum(pipe, params)
            except InsufficientData as exc:
                print(tid, date, "YETERSİZ VERİ", exc.reason)
                continue
            sp = load_spectrum(s, res["result_id"])
            out[tid].append({"result_id": res["result_id"], "date_window": sp["date_window"], "n_points": sp["n_points"], "n_reliable": sp["n_reliable"]})
            print(f"{tid} {sp['date_window']} nokta {sp['n_points']} güvenilir {sp['n_reliable']} → {res['result_id']}")
    db.set_meta("preset_spectra", out)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
