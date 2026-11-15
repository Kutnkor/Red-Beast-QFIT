"""The model-context API must never turn an unknown or visual choice into a measurement."""
import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from blinkspace.api import create_app
from blinkspace.targets import RESOURCES
from tools.build_stellar_profiles import build_catalogue, validate_catalogue


def test_models_api_preserves_unknowns_cited_ranges_and_complete_file_body(settings, pipeline):
    expected = (RESOURCES / "stellar_profiles.json").read_bytes()
    with TestClient(create_app(settings, pipeline, start_workers=False)) as client:
        response = client.get("/api/models")
    assert response.status_code == 200 and response.content == expected
    assert response.headers["cache-control"] == "public, max-age=86400"
    data = response.json()
    assert data == build_catalogue()
    profiles = {entry["target_id"]: entry for entry in data["profiles"]}
    binary = profiles["eps-indi-b"]
    assert binary["parameters"]["teff_k"]["value"] is None
    assert binary["parameters"]["radius_solar"]["classification"] == "unknown"
    for component in binary["components"]:
        assert component["parameters"]["radius_solar"]["value"] is None
        temperature = component["parameters"]["teff_k"]
        assert temperature["range"][0] <= temperature["value"] <= temperature["range"][1]
        assert temperature["classification"] == "computed"
    assert profiles["wise-0855"]["rendering"]["color_mode"] == "dark_visible_light_placeholder"
    mira = profiles["r-dra"]
    source = next(s for s in mira["sources"] if s["id"] == "gcvs-r-dra")
    assert hashlib.sha256((RESOURCES / source["raw_path"]).read_bytes()).hexdigest() == source["response_sha256"]
    assert mira["parameters"]["radius_solar"]["observation_date"] == "1997-07-05"
    assert all(not profile["rendering"]["astrometric_year_changes_stellar_properties"] for profile in data["profiles"])


@pytest.mark.parametrize("mutation", ["uncited_measurement", "invented_unknown", "evolution_clock"])
def test_invalid_scientific_promotions_are_rejected(mutation):
    data = copy.deepcopy(build_catalogue())
    profile = data["profiles"][0]
    if mutation == "uncited_measurement":
        profile["parameters"]["teff_k"]["source_ids"] = []
    elif mutation == "invented_unknown":
        profile["parameters"]["period_days"]["classification"] = "measured"
    else:
        profile["rendering"]["astrometric_year_changes_stellar_properties"] = True
    with pytest.raises(ValueError):
        validate_catalogue(data)
