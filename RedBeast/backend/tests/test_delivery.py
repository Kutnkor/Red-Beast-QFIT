"""Seed export preserves public files while excluding private runtime records."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from blinkspace.db import Database
from tools.build_knowledge import build
from tools.package_seed import TARGETS, package_seed

ROOT = Path(__file__).resolve().parents[2]


def helper(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "docker" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seeded_runtime(tmp_path):
    root = tmp_path / "runtime"
    database = Database(root / "blinkspace.sqlite3")
    mapping = {}
    for index, target in enumerate(sorted(TARGETS)):
        sid = f"preset{index:02d}"
        mapping[target] = sid
        # These are explicitly dummy files for package integrity tests, not science fixtures.
        raw = f"SYNTHETIC packaging fixture {index}".encode()
        sha = hashlib.sha256(raw).hexdigest()
        frame = {"index": 0, "obs_id": "SYNTHETIC", "detector": 1, "mjd_avg": 60000,
                 "lam_um": 1.5, "png": "frame_00.png", "mask_png": "frame_00_mask.png", "npz": "frame_00.npz", "raw_sha256": sha}
        database.put_sequence(sid, sid, sid, "ready", {}, {}, [frame])
        processed = root / "processed" / sid
        processed.mkdir(parents=True)
        for name in ("frame_00.png", "frame_00_mask.png", "frame_00.npz", "track.json"):
            (processed / name).write_text("SYNTHETIC packaging fixture")
        path = root / "raw" / sha[:2] / f"{sha}.fits"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        database.put_raw(f"https://example.invalid/{index}", sha, len(raw))
    database.set_meta("preset_sequences", mapping)
    database.set_meta("private_meta", {"note": "SECRET_METADATA"})
    database.put_sequence("private01", "private01", "private01", "ready", {}, {}, [])
    with database.tx() as connection:
        connection.execute("INSERT INTO shared_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
                           ("private", "preset00", "PRIVATE_TITLE", "SECRET_NOTE", "[]", "{}", "SECRET_KEY_HASH", "test", 0, 0))
    database.add_search("private-search", "private-query", {"note": "SECRET_SEARCH"}, None)
    database.create_job("private-job", "private-query", "search", {"note": "SECRET_JOB"})
    database.close()
    return root, mapping


def test_seed_contains_only_public_presets_and_valid_files(seeded_runtime, tmp_path):
    source, mapping = seeded_runtime
    destination = tmp_path / "seed"
    assert package_seed(source, destination) == mapping
    assert helper("verify_seed").verify_seed(destination) == mapping
    with sqlite3.connect(destination / "blinkspace.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM sequences").fetchone()[0] == 5
        for table in ("shared_observations", "jobs", "searches", "tap_cache", "catalog_cache"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        assert db.execute("SELECT key FROM meta").fetchall() == [("preset_sequences",)]
    # Deleted SQLite records must not remain in free pages in the distributable file.
    assert b"SECRET_" not in (destination / "blinkspace.sqlite3").read_bytes()
    # The original remains intact.
    with sqlite3.connect(source / "blinkspace.sqlite3") as db:
        assert db.execute("SELECT note FROM shared_observations").fetchone()[0] == "SECRET_NOTE"
        assert db.execute("SELECT count(*) FROM sequences").fetchone()[0] == 6


def test_seed_will_not_overwrite_an_existing_directory(seeded_runtime, tmp_path):
    source, _ = seeded_runtime
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "important.txt").write_text("keep")
    with pytest.raises(ValueError, match="already contains"):
        package_seed(source, destination)
    assert (destination / "important.txt").read_text(encoding="utf-8") == "keep"


def test_entrypoint_seeding_never_overwrites_runtime_observations(seeded_runtime, tmp_path):
    source, _ = seeded_runtime
    seed, runtime = tmp_path / "seed", tmp_path / "new-runtime"
    package_seed(source, seed)
    initializer = helper("initialize_data")
    assert initializer.initialize(seed, runtime)
    (runtime / "user-observation.txt").write_text("preserve")
    assert not initializer.initialize(seed, runtime)
    assert (runtime / "user-observation.txt").read_text(encoding="utf-8") == "preserve"


def test_incomplete_release_seed_is_rejected(seeded_runtime, tmp_path):
    source, mapping = seeded_runtime
    seed = tmp_path / "seed"
    package_seed(source, seed)
    (seed / "processed" / mapping["barnard"] / "frame_00.png").unlink()
    with pytest.raises(ValueError, match="missing png"):
        helper("verify_seed").verify_seed(seed)


def test_modified_raw_cutout_is_rejected(seeded_runtime, tmp_path):
    source, _ = seeded_runtime
    seed = tmp_path / "seed"
    package_seed(source, seed)
    next((seed / "raw").rglob("*.fits")).write_bytes(b"CORRUPTED SYNTHETIC packaging fixture")
    with pytest.raises(ValueError, match="checksum mismatch"):
        helper("verify_seed").verify_seed(seed)


def test_knowledge_ids_resolve_and_source_hashes_match():
    bundle = build()
    ids = [chunk["id"] for chunk in bundle["chunks"]]
    assert len(ids) == len(set(ids))
    assert {"motion#model", "epistemic#labels", "method#6"}.issubset(ids)
    for chunk in bundle["chunks"]:
        assert hashlib.sha256((ROOT / chunk["source"]).read_bytes()).hexdigest() == chunk["source_sha256"]
        assert chunk["verification"] == "source_document_only"
    json.dumps(bundle, allow_nan=False)
