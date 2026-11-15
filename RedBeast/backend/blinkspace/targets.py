"""Hazır hedefler (beş hazır hedef). Kayıtlar `tools/build_targets.py` ile SIMBAD'dan üretilir."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent / "resources"


@lru_cache(maxsize=1)
def load_targets_doc() -> dict:
    return json.loads((RESOURCES / "targets.json").read_text(encoding="utf-8"))


def load_targets() -> dict[str, dict]:
    """id -> hedef kaydı."""
    return {t["id"]: t for t in load_targets_doc()["targets"]}


def public_target(t: dict) -> dict:
    """Arayüze gönderilen alanlar."""
    keys = ("id", "name", "kind", "simbad_main_id", "aliases", "object_type", "spectral_type", "ra_deg", "dec_deg",
            "frame", "epoch_jyear", "ra_hms", "dec_dms", "coo_bibcode", "pmra_masyr", "pmdec_masyr", "pm_total_masyr",
            "pm_bibcode", "parallax_mas", "search", "pixels_per_year", "notes", "reference_coords", "primary_star")
    return {k: t[k] for k in keys if k in t}
