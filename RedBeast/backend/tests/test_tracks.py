"""Real pipeline + explicitly synthetic FakeArchive verifies new visual products."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from blinkspace import align
from blinkspace.analysis import Analysis
from blinkspace.api import create_app
from blinkspace.measure import measure_target
from blinkspace.pipeline import SearchParams
from blinkspace.tracks import load_track, precompute_track, predicted_track

from conftest import TARGET, add_matched_series
from test_measure_spectrum import target_record


def make_mover(pipeline, archive, settings):
    add_matched_series(archive, n=4, step_days=180)
    pipeline.targets["mover"] = target_record(archive)
    seq = pipeline.db.get_sequence(pipeline.run(SearchParams(*TARGET, 6.0, target_id="mover"))["sequence_id"])
    return seq, Analysis(settings, pipeline.db, pipeline)


def test_measured_track_is_separate_from_prediction_and_cache(pipeline, archive, settings):
    seq, analysis = make_mover(pipeline, archive, settings)
    fallback = load_track(settings.processed_dir, seq)
    assert fallback["source"] == "predicted_only"
    assert all(f["predicted"] and f["measured"] is None for f in fallback["frames"])
    assert not fallback["status"]["source_detected"]
    doc, measurement = precompute_track(analysis, seq, pipeline.targets["mover"])
    assert doc["source"] == "precomputed" and doc["status"]["source_detected"]
    assert not doc["status"]["change_scientifically_confirmed"]
    assert all(f["measured"]["err_arcsec"] > 0 and f["measured"]["method"] == "flux_weighted_centroid" for f in doc["frames"])
    path = settings.processed_dir / seq["id"] / "track.json"
    path.write_text(json.dumps(doc))
    assert load_track(settings.processed_dir, seq) == doc
    with TestClient(create_app(settings, pipeline, start_workers=False)) as client:
        assert client.get(f"/api/sequences/{seq['id']}/track").json() == doc


def test_comoving_stack_recovers_mover_and_smears_static_star(pipeline, archive, settings):
    seq, analysis = make_mover(pipeline, archive, settings)
    co, invalid, shifts, ref = analysis._track_stack_arrays(seq)
    cube = []
    for i in range(len(seq["frames"])):
        f = analysis._frame(seq, i)
        cube.append(np.where(~f["invalid"] & f["comparable"], analysis._sub(f), np.nan))
    cube = np.asarray(cube)
    count = np.isfinite(cube).sum(axis=0)
    normal = np.where(count >= 2, np.nansum(cube, axis=0) / np.maximum(count, 1), np.nan)
    g = seq["meta"]["grid"]
    w, _ = align.target_grid(*g["crval"], g["nx"] * g["pixscale_arcsec"] / 60)
    pred = seq["frames"][0]["target_predicted"]
    x, y = [int(round(v[0])) for v in w.all_world2pix([pred["ra"]], [pred["dec"]], 0)]
    assert np.nanmax(co[y-4:y+5, x-4:x+5]) > 1.15 * np.nanmax(normal[y-4:y+5, x-4:x+5])
    r, d, _ = archive.stars["s1"]
    x, y = [int(round(v[0])) for v in w.all_world2pix([r], [d], 0)]
    reg_co = np.clip(co[y-5:y+6, x-5:x+6] - 0.1, 0, None)
    reg_normal = np.clip(normal[y-5:y+6, x-5:x+6] - 0.1, 0, None)
    def variance_y(values):
        yy = np.indices(values.shape)[0]
        mean = np.nansum(values * yy) / np.nansum(values)
        return np.nansum(values * (yy - mean)**2) / np.nansum(values)
    assert variance_y(reg_co) > variance_y(reg_normal) * 1.25
    assert shifts[0] == [0.0, 0.0] and ref == 0 and np.isnan(co[invalid]).all()
    with TestClient(create_app(settings, pipeline, start_workers=False)) as client:
        response = client.get(f"/api/sequences/{seq['id']}/track_stack")
        assert response.status_code == 200
        doc = response.json()
        assert "n_detected" not in doc and "n_points" not in doc
        assert set(doc["caveats"]) == {"static_sources_smeared", "proper_motion_only_no_parallax", "display_product_not_photometry"}
        assert client.get(doc["image_url"]).status_code == 200


def test_no_target_gives_none_track_and_422_stack(pipeline, archive, settings):
    add_matched_series(archive, n=3)
    seq = pipeline.db.get_sequence(pipeline.run(SearchParams(*TARGET, 6.0))["sequence_id"])
    with TestClient(create_app(settings, pipeline, start_workers=False)) as client:
        doc = client.get(f"/api/sequences/{seq['id']}/track").json()
        assert doc["source"] == "none" and all(f["measured"] is None and f["predicted"] is None for f in doc["frames"])
        response = client.get(f"/api/sequences/{seq['id']}/track_stack")
        assert response.status_code == 422 and response.json()["error"]["code"] == "no_target_track"


def test_off_grid_target_has_no_measurement(pipeline, archive, settings):
    seq, analysis = make_mover(pipeline, archive, settings)
    for frame in seq["frames"]:
        frame["target_predicted"] = {"ra": TARGET[0] + 1, "dec": TARGET[1]}
    result = measure_target(analysis, seq)
    assert not result["status"]["source_detected"] and result["forced_mean"] is None
    assert all(r["method"] == "off_grid" and r["photometry"]["valid"] is False for r in result["frames"])


def test_one_catalogue_outage_does_not_discard_other_blending_check(pipeline, archive, settings, monkeypatch):
    from blinkspace.measure import blending
    from blinkspace.archive import ArchiveError
    seq, analysis = make_mover(pipeline, archive, settings)
    def unavailable(*args, **kwargs):
        raise ArchiveError("upstream unavailable")
    monkeypatch.setattr(pipeline, "allwise", unavailable)
    rows = [{"pred_ra": TARGET[0], "pred_dec": TARGET[1], "date": f["date_avg"]} for f in seq["frames"]]
    result = blending(analysis, seq, rows, radius_arcsec=200)
    assert result["status"] == "partial" and result["gaia"]
    assert result["unavailable_catalogues"] == {"allwise": "upstream unavailable"}
    assert result["allwise"] == [] and "not establish" in result["note"]


def test_scientific_resources_have_day_cache(settings, pipeline):
    with TestClient(create_app(settings, pipeline, start_workers=False)) as client:
        for route in ("/api/motion", "/api/sky/bright.json", "/api/sky/bright.bin"):
            response = client.get(route)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "public, max-age=86400"
        assert client.get("/api/sky/bright.bin").headers["content-type"] == "application/octet-stream"
