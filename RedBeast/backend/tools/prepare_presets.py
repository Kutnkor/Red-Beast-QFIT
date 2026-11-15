"""Beş hazır hedefin dizilerini önceden hazırlar (ilk açılışın hızlı olması için).

Kullanım:  python -m tools.prepare_presets [--only barnard,r-dra]

Parametreler, arayüzün hazır hedef için göndereceği istekle aynıdır; böylece sunucu aynı diziyi
önbellekten açar. Eşleme `meta.preset_sequences` kaydına yazılır.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from blinkspace.config import load_settings
from blinkspace.db import Database
from blinkspace.pipeline import InsufficientData, Pipeline, SearchParams
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.wavelength import WaveModel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--inventory-dir", type=Path, help="Explicit real archived inventory snapshot; FITS are freshly downloaded and processed")
    a = ap.parse_args()
    s = load_settings()
    db = Database(s.db_path)
    targets = load_targets()
    if a.inventory_dir:
        from tools.inventory_pipeline import InventoryPipeline
        pipe = InventoryPipeline(s, db, WaveModel.load(RESOURCES / "wave_model.json"), targets, inventory_dir=a.inventory_dir)
    else:
        pipe = Pipeline(s, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    only = {x for x in a.only.split(",") if x}
    mapping = db.get_meta("preset_sequences", {})
    log = []
    for tid, t in targets.items():
        if only and tid not in only:
            continue
        params = SearchParams(t["search"]["ra_deg"], t["search"]["dec_deg"], t["search"]["fov_arcmin"], t.get("preferred_lam_um"),
                              0.5, s.default_frames, None, None, tid)
        t0 = time.time()
        print(json.dumps({"target": tid, "stage": "preparing"}), flush=True)
        try:
            res = pipe.run(params)
        except InsufficientData as exc:
            print(f"{tid}: YETERSİZ VERİ {exc.reason}", flush=True)
            log.append({"target": tid, "status": "insufficient_data", "reason": exc.reason})
            continue
        dt = round(time.time() - t0, 1)
        seq = db.get_sequence(res["sequence_id"])
        m = seq["meta"]
        mapping[tid] = seq["id"]
        db.set_meta("preset_sequences", mapping)
        rec = {"target": tid, "sequence_id": seq["id"], "status": seq["status"], "reused": res["reused"], "elapsed_s": dt,
               "n_frames": m["n_frames"], "n_visits": m["n_visits"], "span_days": m["span_days"],
               "lam_ref_um": m["wavelength"]["lam_ref_um"], "warnings": m["warnings"], "timings": m["timings"],
               "alignment_rms_arcsec": m["alignment"].get("rms_arcsec"), "alignment_n": m["alignment"].get("n_measurements")}
        log.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
    print(json.dumps({"preset_sequences": mapping}), flush=True)


if __name__ == "__main__":
    main()
