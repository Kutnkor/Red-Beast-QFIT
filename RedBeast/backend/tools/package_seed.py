"""Export only the five public presets, without user observations or editing tokens.

Run after prepare_presets and precompute_tracks. Uses SQLite's backup API so a running
local server need not be stopped. The source database and source files are never changed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

from blinkspace.config import load_settings

TARGETS = {"barnard", "eps-indi-b", "wise-0855", "rw-aur", "r-dra"}


def package_seed(source: Path, destination: Path) -> dict[str, str]:
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Source and destination must be separate directories.")
    if destination.exists() and any(p.name not in {".gitkeep", "README.md"} for p in destination.iterdir()):
        raise ValueError("Destination already contains data; choose an empty directory.")
    destination.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source / 'blinkspace.sqlite3'}?mode=ro", uri=True) as original:
        row = original.execute("SELECT value FROM meta WHERE key='preset_sequences'").fetchone()
        mapping = json.loads(row[0]) if row else {}
        if set(mapping) != TARGETS:
            raise ValueError("All five presets must be prepared before exporting a release seed.")
        for target, sid in mapping.items():
            if not (source / "processed" / sid / "track.json").is_file():
                raise ValueError(f"Run precompute_tracks first: missing track for {target}")
        with sqlite3.connect(destination / "blinkspace.sqlite3") as copied:
            original.backup(copied)
            placeholders = ",".join("?" for _ in mapping)
            ids = tuple(mapping.values())
            copied.execute(f"DELETE FROM frames WHERE sequence_id NOT IN ({placeholders})", ids)
            copied.execute(f"DELETE FROM sequences WHERE id NOT IN ({placeholders})", ids)
            for table in ("shared_observations", "jobs", "searches", "tap_cache", "catalog_cache"):
                copied.execute(f"DELETE FROM {table}")
            copied.execute("DELETE FROM meta WHERE key != 'preset_sequences'")
            hashes = set()
            for (payload,) in copied.execute("SELECT meta FROM frames"):
                hashes.add(json.loads(payload)["raw_sha256"])
            if hashes:
                copied.execute(f"DELETE FROM raw_files WHERE sha256 NOT IN ({','.join('?' for _ in hashes)})", tuple(hashes))
            else:
                copied.execute("DELETE FROM raw_files")
            copied.commit()
            copied.execute("VACUUM")
            copied.execute("PRAGMA journal_mode=DELETE")
    for sid in mapping.values():
        shutil.copytree(source / "processed" / sid, destination / "processed" / sid)
    for sha in hashes:
        relative = Path("raw") / sha[:2] / f"{sha}.fits"
        (destination / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination / relative)
    (destination / "seed-manifest.json").write_text(json.dumps({
        "schema_version": 1, "preset_sequences": mapping, "raw_cutouts": len(hashes),
        "private_observations_included": False, "source": "NASA/IPAC IRSA SPHEREx Level-2",
    }, indent=2) + "\n", encoding="utf-8")
    return mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path("../seed-data"))
    args = parser.parse_args()
    mapping = package_seed(load_settings().data_dir, args.destination)
    print(f"Exported {len(mapping)} public presets; no user observations or editing keys.")


if __name__ == "__main__":
    main()
