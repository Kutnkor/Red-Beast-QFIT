"""Name -> coordinates resolution.

Deep-sky objects: SIMBAD (via astroquery), with CDS Sesame as a fallback.
Solar System objects: JPL Horizons. Results are catalog data only.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Literal
from urllib.parse import quote_plus

from app.astronomy.data_models import CelestialObject, ResolveResult
from app.astronomy.horizons_client import HorizonsClient, looks_like_solar_system
from app.utils.cache import TTLCache
from app.utils.coordinates import angular_separation_deg
from app.utils.errors import InvalidInputError, QFitError, UpstreamUnavailableError
from app.utils.logging import get_logger
from app.utils.validation import clean_object_name

log = get_logger("resolver")
SIMBAD_HOME = "https://simbad.cds.unistra.fr/simbad/"
SIMBAD_SOURCE = {"name": "SIMBAD (CDS, Strasbourg)", "url": SIMBAD_HOME}
SESAME_SOURCE = {"name": "CDS Sesame name resolver", "url": "https://cds.unistra.fr/cgi-bin/Sesame"}
TargetKind = Literal["auto", "deep_sky", "solar_system"]

OTYPE_ALIASES = {
    "brown dwarf": "BD*", "brown dwarfs": "BD*", "galaxy": "G", "galaxies": "G", "quasar": "QSO",
    "quasars": "QSO", "star": "*", "stars": "*", "supernova": "SN*", "supernovae": "SN*",
    "planetary nebula": "PN", "globular cluster": "GlC", "open cluster": "OpC",
    "white dwarf": "WD*", "white dwarfs": "WD*", "agn": "AGN", "exoplanet": "Pl", "planet": "Pl",
    "young stellar object": "Y*O", "variable star": "V*", "galaxy cluster": "ClG",
    "hii region": "HII", "molecular cloud": "MoC", "pulsar": "Psr", "x-ray binary": "XB*",
}
OTYPE_LABELS = {"G": "Galaxy", "BD*": "Brown dwarf", "QSO": "Quasar", "*": "Star", "PN": "Planetary nebula",
                "GlC": "Globular cluster", "OpC": "Open cluster", "WD*": "White dwarf",
                "AGN": "Active galactic nucleus", "SN*": "Supernova", "Pl": "Extra-solar planet",
                "Y*O": "Young stellar object", "V*": "Variable star", "ClG": "Cluster of galaxies",
                "HII": "HII region", "MoC": "Molecular cloud", "Psr": "Pulsar", "SNR": "Supernova remnant",
                "Sy1": "Seyfert 1 galaxy", "Sy2": "Seyfert 2 galaxy", "**": "Double or multiple star"}
_OTYPE_RE = re.compile(r"^[A-Za-z0-9*?+\-]{1,8}$")


def normalise_otype(text: str | None) -> str | None:
    if not text:
        return None
    code = OTYPE_ALIASES.get(text.strip().lower(), text.strip())
    if not _OTYPE_RE.match(code):
        raise InvalidInputError(
            f"Unknown object type '{text}'. Use a SIMBAD object-type code (e.g. 'BD*', 'G', 'QSO') "
            f"or one of: {', '.join(sorted(set(OTYPE_ALIASES)))}.")
    return code


def _rows(table: Any) -> list[dict[str, Any]]:
    """astropy Table -> list of plain dicts with lower-case keys, masked values as None."""
    if table is None:
        return []
    out = []
    for row in table:
        item = {}
        for col in table.colnames:
            value = row[col]
            if getattr(value, "mask", False) is True or value is None:
                value = None
            elif hasattr(value, "item"):
                value = value.item()
            if isinstance(value, bytes):
                value = value.decode()
            item[col.lower()] = value
        out.append(item)
    return out


class ObjectResolver:
    def __init__(self, horizons: HorizonsClient, *, timeout: float = 45, cache_ttl: float = 600):
        self.horizons = horizons
        self.timeout = timeout
        self.cache = TTLCache(cache_ttl)
        self._simbad_instance: Any = None
        # Circuit breaker: after a SIMBAD failure, skip it for a while instead of paying its
        # timeout on every request (SIMBAD was down all day on 2026-11-14: +5 s per name).
        self._simbad_down_until = 0.0

    # ------------------------------------------------------- blocking seams
    # These three methods are the only places that talk to CDS; tests replace them.
    def _simbad(self) -> Any:
        if self._simbad_instance is None:
            from astroquery.simbad import Simbad
            simbad = Simbad()
            simbad.TIMEOUT = self.timeout
            simbad.add_votable_fields("otype")
            self._simbad_instance = simbad
        return self._simbad_instance

    def _simbad_by_name(self, name: str) -> list[dict[str, Any]]:
        simbad = self._simbad()
        for candidate in (name, f"NAME {name}"):
            rows = _rows(simbad.query_object(candidate))
            if rows:
                return rows
        return []

    def _simbad_name_candidates(self, name: str, limit: int) -> list[dict[str, Any]]:
        adql = (f"SELECT TOP {int(limit)} b.main_id, b.ra, b.dec, b.otype, i.id AS matched_id "
                "FROM basic AS b JOIN ident AS i ON i.oidref = b.oid "
                f"WHERE i.id LIKE 'NAME %{name}%'")
        return _rows(self._simbad().query_tap(adql))

    def _simbad_cone(self, ra: float, dec: float, radius_deg: float, otype: str | None,
                     limit: int) -> list[dict[str, Any]]:
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        simbad = self._simbad()
        simbad.ROW_LIMIT = limit
        criteria = f"otype = '{otype}..'" if otype else None
        table = simbad.query_region(SkyCoord(ra, dec, unit="deg", frame="icrs"),
                                    radius=radius_deg * u.deg, criteria=criteria)
        return _rows(table)

    def _sesame(self, name: str) -> tuple[float, float] | None:
        from astropy.coordinates.name_resolve import NameResolveError, get_icrs_coordinates
        try:
            coord = get_icrs_coordinates(name)
        except NameResolveError:
            return None
        return float(coord.ra.deg), float(coord.dec.deg)

    SIMBAD_RETRY_AFTER_S = 300.0

    async def _simbad_guarded(self, fn, *args) -> Any:
        """SIMBAD call behind the circuit breaker."""
        if time.monotonic() < self._simbad_down_until:
            raise UpstreamUnavailableError("SIMBAD could not be queried (recent failure; retried after a pause).")
        try:
            result = await self._call("SIMBAD", fn, *args)
        except UpstreamUnavailableError:
            self._simbad_down_until = time.monotonic() + self.SIMBAD_RETRY_AFTER_S
            raise
        self._simbad_down_until = 0.0
        return result

    async def _call(self, service: str, fn, *args) -> Any:
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=self.timeout + 5)
        except QFitError:
            raise
        except asyncio.TimeoutError as exc:
            raise UpstreamUnavailableError(f"{service} did not respond in time.") from exc
        except Exception as exc:
            log.warning("catalog service failure", extra={"service": service, "error": type(exc).__name__})
            raise UpstreamUnavailableError(f"{service} could not be queried ({type(exc).__name__}).") from exc

    # ------------------------------------------------------------ public API
    @staticmethod
    def _object_from_row(query: str, row: dict[str, Any]) -> CelestialObject | None:
        if row.get("ra") is None or row.get("dec") is None:
            return None
        main_id = " ".join(str(row.get("main_id") or query).split())
        otype = row.get("otype")
        return CelestialObject(
            query_name=query, name=main_id, ra=float(row["ra"]), dec=float(row["dec"]),
            object_type=otype, object_type_label=OTYPE_LABELS.get(otype or ""),
            matched_identifier=row.get("matched_id"), catalog_source="SIMBAD",
            source_url=f"{SIMBAD_HOME}sim-id?Ident={quote_plus(main_id)}",
            reference_bibcode=row.get("coo_bibcode"))

    async def resolve(self, name: str, target_kind: TargetKind = "auto",
                      epoch_utc: str | None = None) -> ResolveResult:
        name = clean_object_name(name)
        key = (name.lower(), target_kind, epoch_utc)
        if epoch_utc or target_kind != "solar_system":
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        if target_kind == "solar_system" or (target_kind == "auto" and looks_like_solar_system(name)):
            return await self.horizons.resolve(name, epoch_utc)

        try:
            rows = await self._simbad_guarded(self._simbad_by_name, name)
        except UpstreamUnavailableError as outage:
            # SIMBAD down: CDS Sesame (which also queries NED and VizieR) can still give coordinates.
            result = await self._sesame_only(name, outage)
            self.cache.set(key, result)
            return result
        objects = [o for o in (self._object_from_row(name, r) for r in rows) if o]
        distinct = {o.name: o for o in objects}
        if len(distinct) == 1:
            obj = next(iter(distinct.values()))
            result = ResolveResult(status="resolved", query_name=name, object=obj, sources=[SIMBAD_SOURCE],
                                   message=f"SIMBAD resolves '{name}' to {obj.name}.")
        elif len(distinct) > 1:
            result = self._ambiguous(name, list(distinct.values()))
        else:
            result = await self._fallbacks(name, target_kind)
        self.cache.set(key, result)
        return result

    @staticmethod
    def _ambiguous(name: str, objects: list[CelestialObject]) -> ResolveResult:
        return ResolveResult(
            status="ambiguous", query_name=name, sources=[SIMBAD_SOURCE],
            candidates=[{"name": o.name, "ra": o.ra, "dec": o.dec, "object_type": o.object_type,
                         "matched_identifier": o.matched_identifier, "catalog_source": "SIMBAD"}
                        for o in objects],
            message=f"'{name}' matches {len(objects)} different SIMBAD objects. Which one do you mean?")

    async def _sesame_only(self, name: str, outage: UpstreamUnavailableError) -> ResolveResult:
        """Used when SIMBAD cannot be reached. Raises the SIMBAD error if Sesame finds nothing,
        because 'not found' would be a false statement while the main catalog is down."""
        try:
            coords = await self._call("CDS Sesame", self._sesame, name)
        except UpstreamUnavailableError:
            raise outage
        if not coords:
            raise outage
        note = ("SIMBAD could not be reached, so this position comes from CDS Sesame; object type and "
                "catalog identifiers are not available.")
        obj = CelestialObject(query_name=name, name=name, ra=coords[0], dec=coords[1],
                              catalog_source="CDS Sesame", source_url=SESAME_SOURCE["url"], notes=[note])
        return ResolveResult(status="resolved", query_name=name, object=obj, sources=[SESAME_SOURCE],
                             message=f"CDS Sesame resolves '{name}' (SIMBAD was unreachable).")

    async def _fallbacks(self, name: str, target_kind: TargetKind) -> ResolveResult:
        coords = await self._call("CDS Sesame", self._sesame, name)
        if coords:
            obj = CelestialObject(query_name=name, name=name, ra=coords[0], dec=coords[1],
                                  catalog_source="CDS Sesame", source_url=SESAME_SOURCE["url"],
                                  notes=["Resolved by CDS Sesame (SIMBAD/NED/VizieR); no object type available."])
            return ResolveResult(status="resolved", query_name=name, object=obj, sources=[SESAME_SOURCE],
                                 message=f"CDS Sesame resolves '{name}'.")
        try:
            rows = await self._simbad_guarded(self._simbad_name_candidates, name, 8)
        except UpstreamUnavailableError:
            rows = []  # the partial-name search is best effort
        objects = list({o.name: o for o in (self._object_from_row(name, r) for r in rows) if o}.values())
        if len(objects) == 1:
            objects[0].notes.append("Matched by partial name, not by an exact identifier.")
            return ResolveResult(status="resolved", query_name=name, object=objects[0], sources=[SIMBAD_SOURCE],
                                 message=f"SIMBAD has one partial-name match for '{name}': {objects[0].name}.")
        if objects:
            return self._ambiguous(name, objects)
        if target_kind == "auto":
            result = await self.horizons.resolve(name)
            if result.status != "not_found":
                return result
        return ResolveResult(status="not_found", query_name=name, sources=[SIMBAD_SOURCE, SESAME_SOURCE],
                             message=f"No catalog object named '{name}' was found in SIMBAD, CDS Sesame "
                                     "or JPL Horizons. Check the spelling or give coordinates.")

    async def search(self, name: str, max_results: int = 5) -> ResolveResult:
        """Like resolve(), but also offers partial-name matches as candidates."""
        result = await self.resolve(name)
        if result.status == "resolved" and result.object and not result.object.is_solar_system:
            result = result.model_copy(deep=True)
            o = result.object
            result.candidates = [{"name": o.name, "ra": o.ra, "dec": o.dec,
                                  "object_type": o.object_type, "catalog_source": o.catalog_source}]
        result.candidates = result.candidates[:max_results]
        return result

    async def cone_search(self, ra: float, dec: float, radius_deg: float, *,
                          object_type: str | None = None, limit: int = 20) -> dict[str, Any]:
        otype = normalise_otype(object_type)
        rows = await self._simbad_guarded(self._simbad_cone, ra, dec, radius_deg, otype, limit)
        objects = []
        for row in rows:
            obj = self._object_from_row(str(row.get("main_id") or ""), row)
            if obj is None:
                continue
            item = obj.model_dump(include={"name", "ra", "dec", "object_type", "object_type_label",
                                           "catalog_source", "source_url"})
            item["separation_deg"] = round(angular_separation_deg(ra, dec, obj.ra, obj.dec), 6)
            objects.append(item)
        objects.sort(key=lambda o: o["separation_deg"])
        return {"center": {"ra": ra, "dec": dec, "frame": "ICRS"}, "radius_deg": radius_deg,
                "object_type_filter": otype, "count": len(objects), "limit": limit,
                "possibly_truncated": len(rows) >= limit, "objects": objects[:limit],
                "sources": [SIMBAD_SOURCE]}
