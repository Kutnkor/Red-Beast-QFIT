"""Numeric grounding: numbers in an answer must occur in the evidence."""
from __future__ import annotations

import pytest

from app.ai.grounding import unsupported_numbers

EVIDENCE = ['{"ra": 10.684708, "dec": 41.26875, "total": 2200, "t_min_utc": "2026-05-21T05:09:30"}',
            "Band 1: 0.75-1.09 micron, resolving power 39."]


@pytest.mark.parametrize("answer", [
    "M 31 is at RA 10.6847, Dec 41.2688.",            # rounded at the precision written
    "The archive lists 2,200 files.", "Arşivde 2.200 dosya var.",
    "Band 1 covers 0,75-1,09 mikron.",               # Turkish decimal comma
    "It was observed on 2026-05-21.",
    "There are 3 periods and 6 detectors.",           # small counts in prose are not checked
    "Observation spherex_qr3:2026W21_1A_0491_2:D4 and detector D4.",   # identifiers are skipped
    "1. First step\n2. Second step",
    "NGC 224 and Gliese 229 are catalogue names.",
    "| 2026-05-21 05:09:30 | 2026-05-21 05:10:44 |",        # space-separated time, as in model tables
])
def test_supported_answers(answer):
    assert unsupported_numbers(answer, EVIDENCE) == []


@pytest.mark.parametrize("answer,missing", [
    ("The temperature is 1450 K.", ["1450"]),
    ("RA 10.70", ["10.70"]),                           # 10.70 is not 10.6847 at two decimals
    ("Observed on 2025-01-01.", ["2025-01-01"]),
    ("Resolving power 39 and flux 12.5 mJy.", ["12.5"]),
])
def test_unsupported_numbers_are_reported(answer, missing):
    assert unsupported_numbers(answer, EVIDENCE) == missing
