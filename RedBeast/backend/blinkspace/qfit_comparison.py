"""Q-FIT pair selection and evidence from prepared observations."""
from __future__ import annotations

import math
from functools import lru_cache
from itertools import combinations

import numpy as np

from .analysis import AnalysisError, MAX_ALIGNMENT_RMS_ARCSEC, MIN_COMMON_PIXELS, QUANT_TOL, comparable_pixels
from .coords import angular_separation_deg
from .tracks import load_track


def _finite(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def _separation(a, b):
    if not a or not b or any(_finite(p.get(axis)) is None for p in (a, b) for axis in ("ra", "dec")):
        return None
    return round(3600 * angular_separation_deg(a["ra"], a["dec"], b["ra"], b["dec"]), 3)


def compare_observations(analysis, seq: dict, a: int | None = None, b: int | None = None) -> dict:
    frames = seq["frames"]
    if (a is None) != (b is None) or any(i is not None and not 0 <= i < len(frames) for i in (a, b)):
        raise AnalysisError("bad_frame_index")
    track = load_track(analysis.s.processed_dir, seq)
    points = {row["index"]: row for row in track["frames"]}
    alignment = seq["meta"].get("alignment") or {}
    frame_rms = {row["index"]: _finite(row.get("rms_arcsec")) for row in alignment.get("per_frame", [])}
    alignment_rms = _finite(alignment.get("rms_arcsec")) if alignment.get("status") == "ok" else None

    @lru_cache(maxsize=None)
    def mask(i):
        try:
            frame = analysis._frame(seq, i)
            return comparable_pixels(frame) & np.isfinite(frame["image"]) & np.isfinite(frame["background"])
        except (OSError, ValueError, KeyError):
            return None

    def frame_info(i):
        frame = frames[i]
        quality = (frame.get("quality") or {}).get("target") or {}
        saturated = quality.get("saturated")
        return {
            "index": i, "obs_id": frame["obs_id"], "date": frame["date_avg"],
            "wavelength_um": _finite(frame.get("lam_um")), "rms_arcsec": frame_rms.get(i),
            "saturated": saturated if isinstance(saturated, bool) else None,
            "in_cutout": quality.get("in_cutout"),
        }

    def assess(i, j):
        first, last = frame_info(i), frame_info(j)
        rows = [points.get(k, {}) for k in (i, j)]
        measured = [row.get("measured") for row in rows]
        shift = _separation(*measured) if i != j else None
        errors = [_finite((p or {}).get("err_arcsec")) for p in measured]
        uncertainty = round(math.hypot(*errors), 3) if shift is not None and all(e is not None and e > 0 for e in errors) else None
        dt = abs(frames[j]["mjd_avg"] - frames[i]["mjd_avg"])
        offsets = [_finite(frames[k].get("dlam_over_bw")) for k in (i, j)]
        gap = round(abs(offsets[0] - offsets[1]), 4) if None not in offsets else None
        issues = []
        if i == j:
            issues.append("same_frame")
        elif dt == 0:
            issues.append("same_epoch")
        if gap is None:
            issues.append("wavelength_unknown")
        elif gap > QUANT_TOL:
            issues.append("wavelength_mismatch")
        if alignment_rms is None or any(f["rms_arcsec"] is None for f in (first, last)):
            issues.append("alignment_unknown")
        if any(rms is not None and rms > MAX_ALIGNMENT_RMS_ARCSEC
               for rms in (alignment_rms, first["rms_arcsec"], last["rms_arcsec"])):
            issues.append("alignment_large")
        if any(f["in_cutout"] is False or row.get("measured_reason") == "invalid_pixels_at_target"
               for f, row in zip((first, last), rows)):
            issues.append("invalid_target")
        if any(f["saturated"] is None for f in (first, last)):
            issues.append("saturation_unknown")
        if any(f["saturated"] and (p or {}).get("method") != "saturated_core_centroid"
               for f, p in zip((first, last), measured)):
            issues.append("saturated_without_centroid")
        masks = (mask(i), mask(j))
        overlap = common_pixels = None
        if any(m is None for m in masks) or masks[0].shape != masks[1].shape:
            issues.append("overlap_unknown")
        else:
            common_pixels = int(np.count_nonzero(masks[0] & masks[1]))
            overlap = round(common_pixels / masks[0].size, 4) if masks[0].size else 0.0
            if common_pixels < MIN_COMMON_PIXELS:
                issues.append("overlap_small")
        return {
            "a": first, "b": last, "days": round(dt, 4), "gap_bandwidth": gap, "overlap": overlap,
            "common_pixels": common_pixels, "alignment_rms_arcsec": alignment_rms, "issues": issues,
            "measured_shift_arcsec": shift, "estimated_error_arcsec": uncertainty,
            "centroid_methods": [(p or {}).get("method") for p in measured],
            "predicted_shift_arcsec": _separation(*(row.get("predicted") for row in rows)) if i != j else None,
        }

    if a is not None and b is not None:
        result = assess(a, b)
        reasons = result["issues"]
    else:
        # The first eligible pair has the longest baseline. Index order is the stable tie-break.
        indices = sorted(range(len(frames)), key=lambda i: (frames[i]["mjd_avg"], i))
        ranked = sorted(combinations(indices, 2), key=lambda ij: (
            -(frames[ij[1]]["mjd_avg"] - frames[ij[0]]["mjd_avg"]), *ij))
        result, reasons = None, []
        for i, j in ranked:
            pair = assess(i, j)
            if not pair["issues"]:
                result = pair
                break
            reasons.extend(pair["issues"])
        reasons = [] if result else list(dict.fromkeys(reasons or ["need_two_frames"]))
    fit = track.get("motion")
    motion_fit = {key: fit[key] for key in (
        "n_points", "from_date", "to_date", "measured_shift_arcsec", "significance_sigma", "consistent_with_catalog",
    ) if key in fit} if fit else None
    return {
        "sequence_id": seq["id"], "pair": result, "reasons": reasons, "motion_fit": motion_fit,
        "limits": {"gap_bandwidth": QUANT_TOL, "alignment_arcsec": MAX_ALIGNMENT_RMS_ARCSEC, "common_pixels": MIN_COMMON_PIXELS},
    }
