"""Populate an empty runtime directory from the immutable public preset seed."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def initialize(seed: Path, destination: Path) -> bool:
    destination.mkdir(parents=True, exist_ok=True)
    # Never overwrite a runtime database, observations, or partially prepared searches.
    if any(path.name != ".gitkeep" for path in destination.iterdir()):
        return False
    if not (seed / "blinkspace.sqlite3").is_file():
        print("No preset seed in this image; the application will start without cached presets.")
        return False
    for source in seed.iterdir():
        if source.name.startswith(".") or source.name == "README.md":
            continue
        target = destination / source.name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    print("Copied public preset seed to the empty data directory.")
    return True


if __name__ == "__main__":
    initialize(Path(sys.argv[1]), Path(sys.argv[2]))
