from types import SimpleNamespace

import numpy as np

from blinkspace import qfit_comparison as comparison


def test_best_pair_uses_actual_overlap_and_wavelength_and_inspects_requested_pair(monkeypatch, tmp_path):
    frames = [
        {"obs_id": str(i), "date_avg": f"2025-01-0{i + 1}T00:00:00Z", "mjd_avg": 60000 + i,
         "lam_um": 1.5, "dlam_over_bw": gap, "quality": {"target": {"in_cutout": True, "saturated": False}}}
        for i, gap in enumerate([0.0, 0.1, 0.1, 0.6])
    ]
    seq = {"id": "sequence", "frames": frames, "meta": {"alignment": {
        "status": "ok", "rms_arcsec": 0.5, "per_frame": [{"index": i, "rms_arcsec": 0.5} for i in range(4)],
    }}}
    points = [{"index": i, "predicted": {"ra": i / 3600, "dec": 0},
               "measured": {"ra": 2 * i / 3600, "dec": 0, "err_arcsec": 1, "method": "flux_weighted_centroid"}}
              for i in range(4)]
    monkeypatch.setattr(comparison, "load_track", lambda *_: {"frames": points, "motion": {"n_points": 4}})
    masks = np.zeros((4, 10, 10), dtype=bool)
    masks[0, :6] = masks[1, :6] = True
    masks[2:, 4:] = True
    analysis = SimpleNamespace(s=SimpleNamespace(processed_dir=tmp_path),
                               _frame=lambda _, i: {"invalid": ~masks[i], "comparable": masks[i],
                                                     "image": np.ones((10, 10)), "background": 0.0})
    best = comparison.compare_observations(analysis, seq)["pair"]
    assert (best["a"]["index"], best["b"]["index"], best["overlap"]) == (0, 1, 0.6)
    inspected = comparison.compare_observations(analysis, seq, 3, 0)
    pair = inspected["pair"]
    assert (pair["a"]["index"], pair["b"]["index"]) == (3, 0)
    assert pair["measured_shift_arcsec"] == 6 and pair["predicted_shift_arcsec"] == 3
    assert pair["estimated_error_arcsec"] == 1.414
    assert set(inspected["reasons"]) == {"wavelength_mismatch", "overlap_small"}
    assert inspected["motion_fit"]["n_points"] == 4


def test_saturated_core_with_a_centroid_can_support_motion_but_alignment_limits_selection(monkeypatch, tmp_path):
    frames = [
        {"obs_id": str(i), "date_avg": f"2025-01-0{i + 1}T00:00:00Z", "mjd_avg": 60000 + i,
         "lam_um": 1.5, "dlam_over_bw": 0.0, "quality": {"target": {"in_cutout": True, "saturated": True}}}
        for i in range(2)
    ]
    alignment = {"status": "ok", "rms_arcsec": 0.5, "per_frame": [{"index": i, "rms_arcsec": 0.5} for i in range(2)]}
    seq = {"id": "sequence", "frames": frames, "meta": {"alignment": alignment}}
    points = [{"index": i, "measured": {"ra": i / 3600, "dec": 0, "err_arcsec": 1.84, "method": "saturated_core_centroid"}}
              for i in range(2)]
    monkeypatch.setattr(comparison, "load_track", lambda *_: {"frames": points})
    analysis = SimpleNamespace(s=SimpleNamespace(processed_dir=tmp_path),
                               _frame=lambda *_: {"invalid": np.zeros((10, 10), dtype=bool),
                                                   "comparable": np.ones((10, 10), dtype=bool),
                                                   "image": np.ones((10, 10)), "background": 0.0})
    assert comparison.compare_observations(analysis, seq)["pair"]["a"]["saturated"]
    alignment["per_frame"][1]["rms_arcsec"] = 4.0
    result = comparison.compare_observations(analysis, seq)
    assert result["pair"] is None and result["reasons"] == ["alignment_large"]
