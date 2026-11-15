"""Rebuild from a supplied, traceable IRSA inventory while TAP is unavailable.

Only discovery metadata come from CSV. Raw FITS are still downloaded and passed
through the unchanged pipeline, with their actual SHA-256 and native pixels.
This explicit offline-index option is never silently substituted in the API.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path

from blinkspace.archive import Observation, _URI, dedupe
from blinkspace.pipeline import Pipeline


def read_inventory(directory: Path, target_id: str) -> tuple[list[Observation], dict, dict]:
    path = directory / f"{target_id}_observations.csv"
    content = path.read_bytes()
    report_path = directory.parent / "targets" / f"{target_id}.json"
    report_content = report_path.read_bytes()
    report = json.loads(report_content)
    if report["target"]["id"] != target_id:
        raise ValueError("Inventory report target identifier differs")
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8"))))
    observations = []
    for row in rows:
        prefix = "https://irsa.ipac.caltech.edu/"
        if not row["data_url"].startswith(prefix):
            raise ValueError("Inventory contains a non-IRSA URL")
        uri = row["data_url"][len(prefix):]
        match = _URI.fullmatch(uri)
        if not match or int(match["det"]) != int(row["detector"]) or match["tag"] != row["l2_tag"]:
            raise ValueError("Inventory filename/detector/version mismatch")
        footprint = tuple(tuple(float(x) for x in p.split(",")) for p in row["footprint_icrs"].split())
        if len(footprint) != 4 or not all(len(p) == 2 and all(math.isfinite(v) for v in p) for p in footprint):
            raise ValueError("Invalid inventory footprint")
        observations.append(Observation(obs_id=row["obs_id"], detector=int(row["detector"]), collection=row["collection"],
            release=row["release"], l2_tag=row["l2_tag"], l2_version=int(match["ver"]), proc_year=int(match["yr"]),
            proc_doy=int(match["doy"]), pipeline_version=row["pipeline_version"], mjd_start=float(row["mjd_start_utc"]),
            mjd_end=float(row["mjd_end_utc"]), exposure_s=float(row["exposure_s"]), uri=uri, checksum=row["checksum"],
            content_length=int(row["content_length"]), footprint=footprint))
    original = report["inventory"]
    metadata = {"service": "IRSA TAP (bundled inventory snapshot)", "tap_url": original["tap_url"], "adql": original["adql"],
                "rows": len(rows), "parsed": len(observations), "queried_at": report["meta"]["archive"]["queried_at"],
                "cached": True, "elapsed_s": 0.0,
                "inventory_source": {"file": path.name, "sha256": hashlib.sha256(content).hexdigest(),
                    "report_file": report_path.name, "report_sha256": hashlib.sha256(report_content).hexdigest(),
                    "report_generated_at": report["generated_at"],
                    "note": "Bundled real IRSA inventory; not a fresh archive search. Footprint coordinates were rounded by the original CSV exporter. Raw FITS are downloaded and reprocessed."}}
    return observations, metadata, original["query_position"]


class InventoryPipeline(Pipeline):
    def __init__(self, *args, inventory_dir: Path, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory_dir = inventory_dir

    def observations(self, ra, dec, client=None):
        for target_id, target in self.targets.items():
            pos = target["search"]
            if abs(ra - pos["ra_deg"]) < 1e-6 and abs(dec - pos["dec_deg"]) < 1e-6:
                observations, meta, original_pos = read_inventory(self.inventory_dir, target_id)
                if abs(ra - original_pos["ra_deg"]) > 1e-6 or abs(dec - original_pos["dec_deg"]) > 1e-6:
                    raise ValueError("Inventory position differs from requested preset")
                kept, dropped = dedupe(observations)
                meta.update(n_unique=len(kept), n_reprocessed_dropped=len(dropped))
                return kept, dropped, meta
        raise ValueError("Bundled inventory is only valid for its exact preset positions")
