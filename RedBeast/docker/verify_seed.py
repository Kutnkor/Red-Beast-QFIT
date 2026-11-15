"""Fail the release image build when any of the five presets or track caches is absent."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

TARGETS = {"barnard", "eps-indi-b", "wise-0855", "rw-aur", "r-dra"}


def verify_seed(root: Path) -> dict[str, str]:
    db_path = root / "blinkspace.sqlite3"
    if not db_path.is_file():
        raise ValueError("Preset seed database is missing.")
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        checked_hashes = set()
        row = db.execute("SELECT value FROM meta WHERE key='preset_sequences'").fetchone()
        mapping = json.loads(row[0]) if row else {}
        if set(mapping) != TARGETS:
            raise ValueError(f"Five ready presets required; found {sorted(mapping)}")
        for tid, sid in mapping.items():
            sequence = db.execute("SELECT status FROM sequences WHERE id=?", (sid,)).fetchone()
            if sequence is None or sequence[0] != "ready":
                raise ValueError(f"Preset {tid} is not ready.")
            frames = db.execute("SELECT meta FROM frames WHERE sequence_id=?", (sid,)).fetchall()
            if not frames:
                raise ValueError(f"Preset {tid} has no frames.")
            for (payload,) in frames:
                frame = json.loads(payload)
                for key in ("png", "mask_png", "npz"):
                    if not (root / "processed" / sid / frame[key]).is_file():
                        raise ValueError(f"Preset {tid} has a missing {key}.")
                sha = frame["raw_sha256"]
                raw_path = root / "raw" / sha[:2] / f"{sha}.fits"
                if not raw_path.is_file():
                    raise ValueError(f"Preset {tid} has a missing raw cutout.")
                if sha not in checked_hashes:
                    with raw_path.open("rb") as raw:
                        if hashlib.file_digest(raw, "sha256").hexdigest() != sha:
                            raise ValueError(f"Preset {tid} has a raw cutout checksum mismatch.")
                    checked_hashes.add(sha)
            if not (root / "processed" / sid / "track.json").is_file():
                raise ValueError(f"Preset {tid} has no precomputed track.")
    return mapping


if __name__ == "__main__":
    result = verify_seed(Path(sys.argv[1]))
    print(f"Validated {len(result)} public preset sequences and their track caches.")
