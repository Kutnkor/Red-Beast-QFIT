"""Catalog searches and target resolution (catalog data only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.astronomy.data_models import CelestialObject, ResolveResult
from app.astronomy.object_resolver import ObjectResolver, TargetKind
from app.utils.errors import InvalidInputError
from app.utils.validation import validate_ra_dec, validate_radius

MOST_URL = "https://irsa.ipac.caltech.edu/applications/MOST"
COMET_3I_URL = "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html"


@dataclass
class Target:
    status: str  # ok | ambiguous_target | target_not_found | moving_target
    ra: float | None = None
    dec: float | None = None
    object: CelestialObject | None = None
    message: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"ra": self.ra, "dec": self.dec, "frame": "ICRS", "unit": "deg",
                "resolved_from": self.object.query_name if self.object else None}


class SearchService:
    def __init__(self, resolver: ObjectResolver, max_radius_deg: float):
        self.resolver = resolver
        self.max_radius_deg = max_radius_deg

    async def resolve(self, name: str, target_kind: TargetKind = "auto",
                      epoch_utc: str | None = None) -> ResolveResult:
        return await self.resolver.resolve(name, target_kind, epoch_utc)

    async def search_objects(self, name: str, max_results: int = 5) -> ResolveResult:
        return await self.resolver.search(name, max_results)

    async def objects_near(self, ra: float, dec: float, radius_deg: float,
                           object_type: str | None = None, limit: int = 20) -> dict[str, Any]:
        ra, dec = validate_ra_dec(ra, dec)
        radius_deg = validate_radius(radius_deg, self.max_radius_deg)
        result = await self.resolver.cone_search(ra, dec, radius_deg, object_type=object_type, limit=limit)
        result["note"] = ("Catalog entries from SIMBAD. A catalog match is not evidence that "
                          "SPHEREx observed the object; query the SPHEREx archive separately.")
        return result

    async def resolve_target(self, object_name: str | None, ra: float | None,
                             dec: float | None) -> Target:
        """Turn (name | coordinates) into a fixed sky position for an archive search."""
        if ra is not None and dec is not None:
            ra, dec = validate_ra_dec(ra, dec)
            return Target(status="ok", ra=ra, dec=dec)
        if (ra is None) != (dec is None):
            raise InvalidInputError("Provide both RA and Dec, or neither.")
        if not object_name:
            raise InvalidInputError("Provide either an object name or RA and Dec in decimal degrees.")
        result = await self.resolver.resolve(object_name)
        if result.status == "ambiguous":
            return Target(status="ambiguous_target", message=result.message,
                          candidates=result.candidates, sources=result.sources)
        if result.status == "not_found" or result.object is None:
            return Target(status="target_not_found", message=result.message, sources=result.sources)
        obj = result.object
        if obj.position_time_dependent:
            msg = (f"{obj.name} is a Solar System body, so it has no fixed sky position. A search at "
                   f"its position on {obj.position_epoch_utc} would not show when SPHEREx observed it. "
                   f"Use IRSA's Moving Object Search Tool (MOST) for moving targets: {MOST_URL}")
            sources = result.sources + [{"name": "IRSA Moving Object Search Tool", "url": MOST_URL}]
            if "3I" in obj.query_name.upper() or "C/2025 N1" in obj.name.upper():
                msg += f" IRSA also hosts dedicated SPHEREx spectral images of Comet 3I/ATLAS: {COMET_3I_URL}"
                sources.append({"name": "IRSA: SPHEREx spectral images of Comet 3I/ATLAS", "url": COMET_3I_URL})
            return Target(status="moving_target", ra=obj.ra, dec=obj.dec, object=obj, message=msg,
                          sources=sources)
        return Target(status="ok", ra=obj.ra, dec=obj.dec, object=obj, sources=result.sources)
