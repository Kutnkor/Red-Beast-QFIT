"""Catalogue provenance and independent scientific reference tests (no network)."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from blinkspace.targets import RESOURCES
from tools.build_bright_sky import build_rows
from tools.build_motion_catalogue import FIELD_MAP, ID_MAP, convert_star, mamajek_rows
from tools.build_motion_golden import BARNARD_2050, build_document


def test_catalogue_preserves_input_astrometry_and_identifies_estimates():
    raw_bytes = (RESOURCES / "source_data/input_catalogue.json").read_bytes()
    raw = json.loads(raw_bytes)
    doc = json.loads((RESOURCES / "motion_catalogue.json").read_text(encoding="utf-8"))
    assert doc["provenance"]["input_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert len(doc["stars"]) == 120 and len(doc["targets"]) == 5
    assert [s["id"] for s in doc["targets"]] == [ID_MAP[s["id"]] for s in raw["targets"]]
    scientific = ("ra", "dec", "epoch", "parallax", "parallaxError", "pmRa", "pmDec", "radialVelocity", "hasRadialVelocity", "distancePc")
    for key in ("stars", "targets"):
        for original, star in zip(raw[key], doc[key]):
            assert "color" not in star
            assert all(star[k] == original[k] for k in scientific)
            assert (star["teff_k"] is None) == (star["teff_source"] == "none")
            assert star["teff_source"] in ("none", "gaia_gspphot", "mamajek_bprp", "mamajek_sptype") or star["teff_source"].startswith("literature:")
            assert star["rv_kms"] == (original["radialVelocity"] if original["hasRadialVelocity"] else None)
    barnard = doc["targets"][0]
    assert "sim-id?Ident=" in barnard["source_url"] and "Barnard" in barnard["source_url"]
    assert doc["reference"]["moon_mean_diameter_arcsec"]["value"] == 1896
    assert doc["reference"]["obliquity_j2000_deg"]["value"] == pytest.approx(84381.406 / 3600)
    assert doc["reference"]["julian_year_seconds"]["value"] == 31557600


def test_temperature_sources_are_exactly_cached_and_placeholder_colours_not_used():
    doc = json.loads((RESOURCES / "motion_catalogue.json").read_text(encoding="utf-8"))
    for source in doc["provenance"]["temperature_sources"]:
        assert source["url"].startswith("https://") and len(source["sha256"]) == 64 and source["bytes"] > 0
    targets = {s["id"]: s for s in doc["targets"]}
    for tid in ("eps-indi-b", "wise-0855", "rw-aur", "r-dra"):
        assert targets[tid]["bp_rp"] is None
        assert targets[tid]["teff_source"] != "mamajek_bprp"
    assert targets["eps-indi-b"]["teff_k"] is None  # never invent an unresolved system's one temperature
    assert [c["teff_range_k"] for c in targets["eps-indi-b"]["components"]] == [[1300, 1340], [880, 940]]


def test_bright_sky_real_catalogue_binary_and_input_checksums():
    meta = json.loads((RESOURCES / "bright_sky.json").read_text(encoding="utf-8"))
    blob = (RESOURCES / "bright_sky.bin").read_bytes()
    data = np.frombuffer(blob, dtype="<f4").reshape((-1, 7))
    assert 7000 <= meta["count"] <= 11000
    assert len(blob) == meta["count"] * 7 * 4 == meta["bytes"]
    assert len(meta["hip_ids"]) == len(set(meta["hip_ids"])) == len(data)
    assert hashlib.sha256(blob).hexdigest() == meta["sha256"]
    assert np.allclose(np.linalg.norm(data[:, :3], axis=1), 1, atol=1e-6)
    assert (data[:, 3] < 6.5).all() and (data[:, 4:] >= 0).all() and (data[:, 4:] <= 1).all()
    assert "ESA" in meta["partner_data"]
    schema = meta["provenance"]["schema"]
    assert schema["adql"].startswith("SELECT column_name") if schema["adql"] else "asu-tsv" in schema["url"]


def test_bright_sky_unknown_colour_is_neutral_and_proper_motion_is_applied():
    rows = [{"HIP": "1", "RAICRS": "0", "DEICRS": "0", "Vmag": "2", "B-V": "", "pmRA": "1000", "pmDE": "0"},
            {"HIP": "2", "RAICRS": "0", "DEICRS": "90", "Vmag": "3", "B-V": ".65", "pmRA": "", "pmDE": ""}]
    array, hips, counts = build_rows(rows)
    assert hips == [1, 2] and counts["neutral_colour_count"] == 1 and counts["missing_proper_motion_count"] == 1
    assert array[0, 4:].tolist() == [1, 1, 1]
    assert array[0, 2] == pytest.approx(np.deg2rad(34.75 / 3600), rel=1e-6)
    assert array[1, 1] == pytest.approx(1)


def test_independent_astropy_golden_is_reproducible():
    content = (RESOURCES / "source_data/input_catalogue.json").read_bytes()
    built = build_document(json.loads(content), hashlib.sha256(content).hexdigest())
    path = Path(__file__).resolve().parents[2] / "frontend/src/tests/golden/motion.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert built["stars"] == saved["stars"]
    assert len(built["stars"]) == 5
    actual = next(p["icrs_pc"] for s in built["stars"] if s["id"] == "barnard" for p in s["positions"] if p["year"] == 2050)
    assert np.allclose(actual, BARNARD_2050, rtol=0, atol=1e-12)
