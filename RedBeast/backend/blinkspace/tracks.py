"""Separate measured source positions from catalogue-only predictions.

GET never performs network requests or expensive measurements. A prepared track
is served if available; otherwise the response explicitly says predicted_only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import align
from .measure import CENTROID_ERR_PX, CENTROID_FLOOR_PX, DETECT_SNR, measure_target


def _prediction(frame: dict) -> dict | None:
    p = frame.get("target_predicted")
    if not p or not all(isinstance(p.get(k), (int, float)) and math.isfinite(p[k]) for k in ("ra", "dec")):
        return None
    return {"ra": p["ra"], "dec": p["dec"], "method": "proper_motion_only"}


def predicted_track(seq: dict) -> dict:
    frames = [{"index": f["index"], "mjd": f["mjd_avg"], "date": f["date_avg"], "predicted": _prediction(f),
               "measured": None, "measured_reason": "not_precomputed" if _prediction(f) else "no_target_prediction"}
              for f in seq["frames"]]
    return {"sequence_id": seq["id"], "target_id": seq["params"].get("target_id"),
            "source": "predicted_only" if any(f["predicted"] for f in frames) else "none", "frames": frames,
            "motion": None, "status": {"data_available": len(frames) >= 2, "source_detected": False,
            "change_seen": False, "change_kind": None, "change_scientifically_confirmed": False},
            "caveats": ["proper_motion_only_no_parallax", "predictions_are_not_detections"]}


def load_track(processed_dir: Path, seq: dict) -> dict:
    path = processed_dir / seq["id"] / "track.json"
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("sequence_id") == seq["id"] and doc.get("data_fingerprint") == seq["meta"].get("data_fingerprint"):
            return doc
    return predicted_track(seq)


def precompute_track(analysis, seq: dict, target: dict | None = None) -> tuple[dict, dict | None]:
    doc = predicted_track(seq)
    # For a coordinate-only search the centre is not an identified target.
    if not any(f["predicted"] for f in doc["frames"]):
        return doc, None
    measurement = measure_target(analysis, seq, target)
    doc["source"] = "precomputed"
    doc["data_fingerprint"] = seq["meta"].get("data_fingerprint")
    doc["motion"] = measurement["motion"]
    doc["status"] = measurement["status"]
    doc["forced_mean"] = measurement.get("forced_mean")
    doc["blending"] = measurement.get("blending")
    doc["caveats"] = ["proper_motion_only_no_parallax", "scientific_confirmation_requires_follow_up"]
    by_index = {r["index"]: r for r in measurement["frames"]}
    al = seq["meta"].get("alignment", {})
    for frame in doc["frames"]:
        row = by_index[frame["index"]]
        detected = row.get("method") == "saturated_core_centroid" or (row.get("snr") is not None and row["snr"] >= DETECT_SNR)
        if row.get("ra") is None or row.get("dec") is None:
            frame["measured_reason"] = row.get("method") or "centroid_unavailable"
        elif not detected:
            frame["measured_reason"] = "below_detection_threshold"
        else:
            if measurement["motion"]:
                error = measurement["motion"]["per_point_error_arcsec"]
            elif row["method"] == "flux_weighted_centroid" and al.get("status") == "ok" and al.get("rms_arcsec"):
                error = max(float(al["rms_arcsec"]), CENTROID_FLOOR_PX * align.NATIVE_PIXSCALE_ARCSEC)
            else:
                error = CENTROID_ERR_PX * align.NATIVE_PIXSCALE_ARCSEC
            frame["measured"] = {"ra": row["ra"], "dec": row["dec"], "err_arcsec": error, "method": row["method"]}
            frame["measured_reason"] = None
    return doc, measurement
