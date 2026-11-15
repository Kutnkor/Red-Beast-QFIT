"""SPHEREx observation searches. Availability is always decided by the archive
response for this exact query, never by a catalog match."""
from __future__ import annotations

from typing import Any, Sequence

from app.astronomy.data_models import IMAGE_COLLECTIONS, SPHEREX_COLLECTIONS, SpherexProduct
from app.astronomy.spherex_client import SpherexClient
from app.services.search_service import SearchService, Target
from app.utils.coordinates import iso_to_mjd, mjd_to_iso
from app.utils.errors import InvalidInputError, NotFoundError
from app.utils.validation import validate_radius

DEFAULT_RADIUS_DEG = 0.003  # ~10 arcsec: "which images cover this position"
IRSA_SOURCES = [
    {"name": "NASA/IPAC Infrared Science Archive (IRSA) - SPHEREx", "url": "https://irsa.ipac.caltech.edu/Missions/spherex.html"},
    {"name": "IRSA Simple Image Access v2 service", "url": "https://irsa.ipac.caltech.edu/ibe/sia.html"},
]
NO_DATA_REASONS = [
    "The position may not have been covered yet by the released data (searchable releases: DR1 and QR3).",
    "Newly ingested exposures reach the SIA2 search service about a day after other IRSA interfaces.",
    "QR2 products are no longer searchable through SIA2.",
    "Filters in the request (detector, release, dates) may exclude the exposures that exist.",
]
_EXCLUDE = {"footprint", "extra"}


def collections_for(release: str | None) -> list[str]:
    release = (release or "all").lower()
    if release == "all":
        return list(IMAGE_COLLECTIONS)
    chosen = [c for c in IMAGE_COLLECTIONS if SPHEREX_COLLECTIONS[c]["release"].lower() == release]
    if not chosen:
        raise InvalidInputError("release must be one of: all, dr1, qr3.")
    return chosen


def dump(product: SpherexProduct, include_footprint: bool = False) -> dict[str, Any]:
    return product.model_dump(exclude=None if include_footprint else _EXCLUDE)


def summarise(products: Sequence[SpherexProduct]) -> dict[str, Any]:
    times = [p.t_min_mjd for p in products if p.t_min_mjd is not None]
    ends = [p.t_max_mjd for p in products if p.t_max_mjd is not None]
    return {
        "products": len(products),
        "exposures": len({p.obs_id for p in products}),
        "detectors": sorted({p.detector for p in products if p.detector}),
        "collections": sorted({p.collection for p in products}),
        "first_observation_utc": mjd_to_iso(min(times)) if times else None,
        "last_observation_utc": mjd_to_iso(max(ends)) if ends else None,
    }


def group_periods(products: Sequence[SpherexProduct], gap_days: float) -> list[dict[str, Any]]:
    """Group exposures into observation periods separated by more than `gap_days`."""
    dated = sorted((p for p in products if p.t_min_mjd is not None), key=lambda p: p.t_min_mjd)
    groups: list[list[SpherexProduct]] = []
    for product in dated:
        if groups and product.t_min_mjd - (groups[-1][-1].t_max_mjd or groups[-1][-1].t_min_mjd) <= gap_days:
            groups[-1].append(product)
        else:
            groups.append([product])
    periods = []
    for index, group in enumerate(groups, start=1):
        start = group[0].t_min_mjd
        end = max(p.t_max_mjd or p.t_min_mjd for p in group)
        periods.append({"period": index, "start_utc": mjd_to_iso(start), "end_utc": mjd_to_iso(end),
                        "start_mjd": start, "end_mjd": end, "duration_days": round(end - start, 4),
                        **{k: v for k, v in summarise(group).items()
                           if k in ("products", "exposures", "detectors", "collections")}})
    return periods


def blocked_target(target: Target) -> dict[str, Any]:
    """Result for a target that could not be turned into a fixed position."""
    return {"status": target.status, "spherex_available": None, "target": target.as_dict(),
            "object": target.object.model_dump() if target.object else None,
            "candidates": target.candidates, "message": target.message,
            "observations": [], "total": 0, "sources": target.sources}


class ObservationService:
    def __init__(self, spherex: SpherexClient, search: SearchService, max_radius_deg: float):
        self.spherex = spherex
        self.search = search
        self.max_radius_deg = max_radius_deg

    async def _fetch(self, target: Target, radius_deg: float, release: str | None,
                     detector: int | None, start_utc: str | None, end_utc: str | None,
                     ) -> tuple[list[SpherexProduct], bool, list[str]]:
        collections = collections_for(release)
        time_mjd = None
        if start_utc or end_utc:
            try:
                time_mjd = (iso_to_mjd(start_utc) if start_utc else 0.0,
                            iso_to_mjd(end_utc) if end_utc else 99999.0)
            except ValueError as exc:
                raise InvalidInputError("start_utc / end_utc must be ISO-8601 dates.") from exc
            if time_mjd[0] > time_mjd[1]:
                raise InvalidInputError("start_utc must be before end_utc.")
        products, truncated = await self.spherex.search_products(
            target.ra, target.dec, radius_deg, collections=collections, time_mjd=time_mjd)
        if detector is not None:
            products = [p for p in products if p.detector == detector]
        return products, truncated, collections

    async def search_observations(self, *, object_name: str | None = None, ra: float | None = None,
                                  dec: float | None = None, radius_deg: float = DEFAULT_RADIUS_DEG,
                                  limit: int = 50, offset: int = 0, detector: int | None = None,
                                  release: str | None = None, start_utc: str | None = None,
                                  end_utc: str | None = None, include_footprint: bool = False,
                                  ) -> dict[str, Any]:
        radius_deg = validate_radius(radius_deg, self.max_radius_deg)
        target = await self.search.resolve_target(object_name, ra, dec)
        if target.status != "ok":
            return blocked_target(target)
        products, truncated, collections = await self._fetch(target, radius_deg, release, detector,
                                                             start_utc, end_utc)
        page = products[offset:offset + limit]
        available = len(products) > 0
        result: dict[str, Any] = {
            "status": "ok" if available else "no_data",
            "spherex_available": available,
            "target": {**target.as_dict(), "radius_deg": radius_deg},
            "object": target.object.model_dump() if target.object else None,
            "total": len(products), "returned": len(page), "offset": offset, "limit": limit,
            "has_more": offset + len(page) < len(products),
            "truncated_by_archive_limit": truncated,
            "collections_searched": collections,
            "filters": {"detector": detector, "release": release or "all",
                        "start_utc": start_utc, "end_utc": end_utc},
            "summary": summarise(products),
            "observations": [dump(p, include_footprint) for p in page],
            "sources": target.sources + IRSA_SOURCES,
        }
        if available:
            s = result["summary"]
            result["message"] = (
                f"The IRSA archive lists {s['products']} SPHEREx spectral image file(s) from "
                f"{s['exposures']} exposure(s) covering this position, taken between "
                f"{s['first_observation_utc']} and {s['last_observation_utc']}.")
        else:
            result["message"] = "The IRSA archive returned no SPHEREx spectral images for this position and filters."
            result["possible_reasons"] = NO_DATA_REASONS
        return result

    async def get_observation(self, observation_id: str, ra: float | None = None,
                              dec: float | None = None) -> dict[str, Any]:
        hint = (ra, dec) if ra is not None and dec is not None else None
        products = await self.spherex.get_products_by_id(observation_id, position_hint=hint)
        if not products:
            raise NotFoundError(f"The IRSA archive has no SPHEREx product with id '{observation_id}'.")
        return {"status": "ok", "observation_id": observation_id, "count": len(products),
                "products": [dump(p, include_footprint=True) for p in products],
                "message": f"Archive metadata for {len(products)} file(s) of observation {products[0].obs_id}.",
                "sources": IRSA_SOURCES}

    async def observation_periods(self, *, object_name: str | None = None, ra: float | None = None,
                                  dec: float | None = None, radius_deg: float = DEFAULT_RADIUS_DEG,
                                  gap_days: float = 20.0, release: str | None = None) -> dict[str, Any]:
        radius_deg = validate_radius(radius_deg, self.max_radius_deg)
        target = await self.search.resolve_target(object_name, ra, dec)
        if target.status != "ok":
            return {**blocked_target(target), "periods": []}
        products, truncated, collections = await self._fetch(target, radius_deg, release, None, None, None)
        periods = group_periods(products, gap_days)
        available = bool(products)
        message = (f"SPHEREx covered this position in {len(periods)} observation period(s) "
                   f"(exposures grouped when less than {gap_days:g} days apart)."
                   if available else "The IRSA archive returned no SPHEREx spectral images for this position.")
        result = {"status": "ok" if available else "no_data", "spherex_available": available,
                  "target": {**target.as_dict(), "radius_deg": radius_deg},
                  "object": target.object.model_dump() if target.object else None,
                  "period_gap_days": gap_days, "period_count": len(periods), "periods": periods,
                  "summary": summarise(products), "collections_searched": collections,
                  "truncated_by_archive_limit": truncated, "message": message,
                  "sources": target.sources + IRSA_SOURCES}
        if not available:
            result["possible_reasons"] = NO_DATA_REASONS
        return result
