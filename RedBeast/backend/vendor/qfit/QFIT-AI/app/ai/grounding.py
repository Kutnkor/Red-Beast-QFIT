"""Numeric grounding check: which numbers in an answer are not backed by evidence?

A deterministic guard against fabricated measurements. It does not judge wording; it
only asks, for every number and date in the model's text, whether the same value
(at the precision the model wrote it) occurs in the evidence the model was given.
"""
from __future__ import annotations

import re

# Date with an optional time, written either ISO style (2025-08-14T21:33:28Z) or with a space
# (2025-08-14 21:33:28), as models do in tables.
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?)?")
_IDENT = re.compile(r"\b(?:[A-Za-z]+[\w\-/+:]*\d[\w\-/+:.]*|\d+[A-Za-z_][\w\-/+:]*)")
_CATALOG_NAME = re.compile(r"\b(?:M|NGC|IC|HD|HIP|HR|GJ|Gliese|Messier|UGC|PGC|Abell|Teide|Calar)\s+\d+[A-Za-z]?\b")
_LIST_MARK = re.compile(r"^\s*\d+[.)]\s", re.M)
_NUMBER = re.compile(r"(?<![\w.])[-+]?\d[\d.,]*(?:[eE][-+]?\d+)?")
_GROUPED = re.compile(r"^\d{1,3}([.,]\d{3})+$")
SMALL_INTEGER_LIMIT = 10


def _interpretations(token: str) -> list[tuple[float, int]]:
    """Possible readings of a numeric token as (value, decimals). Handles 2,200 / 2.200
    (thousands) and 0,75 (Turkish decimal comma)."""
    token = token.strip().rstrip(".,").lstrip("+")
    out: list[tuple[float, int]] = []

    def add(text: str) -> None:
        try:
            value = float(text)
        except ValueError:
            return
        mantissa = text.lower().split("e")[0]
        out.append((value, len(mantissa.split(".")[1]) if "." in mantissa else 0))

    if _GROUPED.match(token.lstrip("-")):
        add(token.replace(",", "").replace(".", ""))
    if "," in token and "." in token:
        add(token.replace(",", ""))
        add(token.replace(".", "").replace(",", "."))
    elif "," in token:
        add(token.replace(",", "."))
        add(token.replace(",", ""))
    else:
        add(token)
    return out


def _numbers(text: str) -> list[str]:
    text = _DATE.sub(" ", text)
    text = _CATALOG_NAME.sub(" ", text)          # "M 31", "NGC 224": names, not measurements
    text = _IDENT.sub(" ", text)
    text = _LIST_MARK.sub(" ", text)
    return [m.group(0) for m in _NUMBER.finditer(text) if any(ch.isdigit() for ch in m.group(0))]


def unsupported_numbers(answer: str, evidence: list[str]) -> list[str]:
    """Numbers and dates in `answer` that do not occur in any evidence text."""
    joined = "\n".join(evidence)
    missing: list[str] = []
    for date in _DATE.findall(answer):
        if date[:10] not in joined and date not in missing:
            missing.append(date)
    known = {abs(value) for token in set(_NUMBER.findall(joined)) for value, _ in _interpretations(token)}
    for token in _numbers(answer):
        readings = _interpretations(token)
        if not readings:
            continue
        if any(decimals == 0 and abs(value) <= SMALL_INTEGER_LIMIT for value, decimals in readings):
            continue                                  # counts and ordinals in ordinary prose
        supported = any(abs(k - abs(value)) <= 0.5 * 10 ** -decimals + 1e-12
                        for value, decimals in readings for k in known)
        shown = token.rstrip(".,")
        if not supported and shown not in missing:
            missing.append(shown)
    return missing
