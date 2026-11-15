"""WISE 0855: otomatik seçilen (kısa) dalga boyunda zorlanmış fotometri.

Kullanım:  python -m tools.wise0855_wavelength_check

"Neden uygun dalga boyu gerekir?" öğretici görevinin yanıt anahtarı için: aynı hedef, hattın dalga boyu
belirtilmeden seçtiği grupta hazırlanır ve öngörülen konumlardaki akı ölçülür. Sonuç `meta` kaydına yazılır.
"""
from __future__ import annotations

import json

from blinkspace.analysis import Analysis
from blinkspace.config import load_settings
from blinkspace.db import Database
from blinkspace.measure import measure_target
from blinkspace.pipeline import Pipeline, SearchParams
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.wavelength import WaveModel


def main() -> None:
    s = load_settings()
    db = Database(s.db_path)
    targets = load_targets()
    pipe = Pipeline(s, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    t = targets["wise-0855"]
    res = pipe.run(SearchParams(t["search"]["ra_deg"], t["search"]["dec_deg"], t["search"]["fov_arcmin"], None, 0.5, s.default_frames, None, None, "wise-0855"))
    seq = db.get_sequence(res["sequence_id"])
    m = measure_target(Analysis(s, db, pipe), seq, t)
    fm = m["forced_mean"]
    out = {"sequence_id": seq["id"], "lam_um": seq["meta"]["wavelength"]["lam_ref_um"], "n_frames": len(seq["frames"]),
           "obs_ids": [f["obs_id"] for f in seq["frames"]], **(fm or {})}
    db.set_meta("wise0855_auto_wavelength_check", out)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    for r in m["frames"]:
        ph = r["photometry"]
        print("  ", r["date"][:10], "S/N", r["snr"], "akı", None if ph["flux_mjy"] is None else round(ph["flux_mjy"], 3), ph["reason"])


if __name__ == "__main__":
    main()
