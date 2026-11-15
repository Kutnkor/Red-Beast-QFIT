"""Input validation shared by the API layer and the AI tool layer."""
from __future__ import annotations

import math
import re

from app.utils.errors import InvalidInputError

# Characters allowed in an object name. Quotes are rejected so a name can never
# break out of an ADQL string literal.
_NAME_RE = re.compile(r"^[\w\s\-+.*/()\[\]:,#]+$", re.UNICODE)
_COLLECTION_RE = re.compile(r"^spherex_[a-z0-9_]+$")
_OBS_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_PRODUCT_RE = re.compile(r"^[A-Za-z0-9]+$")


def validate_ra_dec(ra: float, dec: float) -> tuple[float, float]:
    if ra is None or dec is None or not (math.isfinite(ra) and math.isfinite(dec)):
        raise InvalidInputError("RA and Dec must be finite numbers in decimal degrees.")
    if not 0.0 <= ra <= 360.0:
        raise InvalidInputError(f"RA must be within 0-360 degrees (got {ra}).")
    if not -90.0 <= dec <= 90.0:
        raise InvalidInputError(f"Dec must be within -90 to +90 degrees (got {dec}).")
    return (0.0 if ra == 360.0 else float(ra)), float(dec)


def validate_radius(radius_deg: float, max_deg: float) -> float:
    if radius_deg is None or not math.isfinite(radius_deg) or radius_deg <= 0:
        raise InvalidInputError("Search radius must be a positive number of degrees.")
    if radius_deg > max_deg:
        raise InvalidInputError(f"Search radius {radius_deg} deg exceeds the maximum of {max_deg} deg.")
    return float(radius_deg)


def clean_object_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise InvalidInputError("Object name must not be empty.")
    if len(name) > 100:
        raise InvalidInputError("Object name is too long (max 100 characters).")
    if not _NAME_RE.match(name):
        raise InvalidInputError("Object name contains unsupported characters.")
    return name


def parse_observation_id(observation_id: str) -> tuple[str | None, str, str | None]:
    """Split a Q-FIT observation id into (collection, obs_id, product).

    Accepted forms:
      spherex_qr3:2026W21_1A_0491_2:D4   one detector image
      spherex_qr3:2026W21_1A_0491_2      every detector of that exposure
      2026W21_1A_0491_2                  the exposure in any collection
    """
    parts = (observation_id or "").strip().split(":")
    if len(parts) == 1:
        collection, obs_id, product = None, parts[0], None
    elif len(parts) == 2:
        collection, obs_id, product = parts[0], parts[1], None
    elif len(parts) == 3:
        collection, obs_id, product = parts
    else:
        raise InvalidInputError("Malformed observation id.")
    if collection is not None and not _COLLECTION_RE.match(collection):
        raise InvalidInputError("Malformed observation id (collection).")
    if not _OBS_ID_RE.match(obs_id) or len(obs_id) > 64:
        raise InvalidInputError("Malformed observation id.")
    if product is not None and not _PRODUCT_RE.match(product):
        raise InvalidInputError("Malformed observation id (product).")
    return collection, obs_id, product
