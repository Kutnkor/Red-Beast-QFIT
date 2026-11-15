"""Coordinate and time helpers. Angles are ICRS decimal degrees; times are UTC."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

_MJD_EPOCH = datetime(1858, 11, 17, tzinfo=timezone.utc)
JD_MINUS_MJD = 2400000.5


def mjd_to_iso(mjd: float | None) -> str | None:
    if mjd is None or not math.isfinite(mjd):
        return None
    return (_MJD_EPOCH + timedelta(days=mjd)).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc(text: str) -> datetime:
    """Parse an ISO-8601 date or datetime; naive values are taken as UTC."""
    dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def datetime_to_mjd(dt: datetime) -> float:
    return (dt - _MJD_EPOCH).total_seconds() / 86400.0


def iso_to_mjd(text: str) -> float:
    return datetime_to_mjd(parse_utc(text))


def meters_to_microns(value: float | None) -> float | None:
    return None if value is None else round(value * 1e6, 5)


def angular_separation_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    a = math.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * math.cos(d2) * math.sin((r2 - r1) / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(a))))


def healpix_order5_note() -> str:
    return "All-Sky Cube tiles are HEALPix order 5 (NESTED), about 1.8 deg on a side."
