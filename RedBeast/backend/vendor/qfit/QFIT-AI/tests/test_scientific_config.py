"""research/data.json loader. The real file is not in this repository yet, so these tests use
small files written by the test; they check loading behaviour, never a threshold value."""
from __future__ import annotations

import json
import os
import time

from app.scientific.config_loader import ScientificConfig, inspect_structure


def test_missing_file_is_reported_not_invented(tmp_path):
    status = ScientificConfig(tmp_path / "data.json").load()
    assert status["status"] == "missing" and "not found" in status["message"]
    assert ScientificConfig(tmp_path / "data.json").get("anything") is None


def test_invalid_json_is_reported_with_position(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"a": 1,,}', encoding="utf-8")
    status = ScientificConfig(path).load()
    assert status["status"] == "invalid" and "line 1" in status["message"]


def test_loaded_file_is_versioned_read_only_and_reloaded_on_change(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"version": "3", "phases": {"main": {"tr": "Ana kol", "en": "Main sequence"}}}),
                    encoding="utf-8")
    before = path.read_bytes()
    config = ScientificConfig(path)
    status = config.load()
    assert status["status"] == "loaded" and status["declared_version"] == "3"
    assert config.version.startswith("3+") and status["bilingual_nodes"] == 1 and status["problems"] == []
    assert config.get("phases.main.en") == "Main sequence" and config.get("phases.nope") is None
    assert ScientificConfig.localized(config.get("phases.main"), "tr") == "Ana kol"
    assert ScientificConfig.localized({"en": "x"}, "tr") is None          # never a silent fallback
    assert path.read_bytes() == before
    first = config.version
    path.write_text(json.dumps({"version": "4"}), encoding="utf-8")
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert config.version != first and config.version.startswith("4+")


def test_structure_problems_are_found_not_fixed():
    report = inspect_structure({"a": {"temp_min": 10, "temp_max": 5}, "b": {"min": 3, "max": 1},
                                "c": {"tr": "metin"}, "d": {"tr": "x", "en": ""}, "e": {"threshold": "5"}})
    problems = " | ".join(report["problems"])
    assert "temp_min (10) is greater than temp_max (5)" in problems and "min (3) is greater than max (1)" in problems
    assert "has 'tr' text but no 'en' text" in problems and "empty 'en' text" in problems
    assert "threshold is text" in problems
