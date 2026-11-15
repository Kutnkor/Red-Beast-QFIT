"""Prepare measured tracks after prepare_presets (network catalogue checks may run).

Run: PYTHONPATH=backend python -m tools.precompute_tracks [--only barnard,r-dra]
Cached tracks are reused unless --refresh is supplied. Raw measurements are saved
alongside track.json for audit; they are not exposed as unqualified detections.
"""
from __future__ import annotations

import argparse
import json

from blinkspace.analysis import Analysis
from blinkspace.config import load_settings
from blinkspace.db import Database
from blinkspace.pipeline import Pipeline
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.tracks import load_track, precompute_track
from blinkspace.wavelength import WaveModel
from tools.science_sources import write_json


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    settings = load_settings()
    db = Database(settings.db_path)
    targets = load_targets()
    pipeline = Pipeline(settings, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    analysis = Analysis(settings, db, pipeline)
    mapping = db.get_meta("preset_sequences", {})
    only = {s for s in args.only.split(",") if s}
    if not mapping:
        raise SystemExit("No prepared sequences; run tools.prepare_presets first")
    for target_id, seq_id in mapping.items():
        if only and target_id not in only:
            continue
        seq = db.get_sequence(seq_id)
        if seq is None:
            raise RuntimeError(f"Missing prepared sequence: {target_id} {seq_id}")
        cached = load_track(settings.processed_dir, seq)
        if cached["source"] == "precomputed" and not args.refresh:
            print(json.dumps({"target_id": target_id, "sequence_id": seq_id, "source": "cached", "status": cached["status"]}), flush=True)
            continue
        doc, measurement = precompute_track(analysis, seq, targets.get(target_id))
        write_json(settings.processed_dir / seq_id / "track.json", doc)
        if measurement:
            write_json(settings.processed_dir / seq_id / "target_measurement.json", measurement)
        print(json.dumps({"target_id": target_id, "sequence_id": seq_id, "source": doc["source"], "status": doc["status"]}), flush=True)


if __name__ == "__main__":
    main()
