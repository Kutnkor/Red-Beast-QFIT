"""Solar System object positions from the JPL Horizons API.

Uses the documented REST interface (https://ssd-api.jpl.nasa.gov/doc/horizons.html):
  GET horizons.api?format=text&COMMAND='<target>'&EPHEM_TYPE=OBSERVER&CENTER='500@399'
      &TLIST='<JD>'&QUANTITIES='1'&ANG_FORMAT=DEG&CSV_FORMAT=YES
Quantity 1 is the astrometric RA/Dec in the ICRF, here for a geocentric observer.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.astronomy.archive_client import ArchiveClient
from app.astronomy.data_models import CelestialObject, ResolveResult
from app.utils.coordinates import JD_MINUS_MJD, datetime_to_mjd, parse_utc
from app.utils.errors import InvalidInputError, UpstreamError

HORIZONS_HOME = "https://ssd.jpl.nasa.gov/horizons/"
MAJOR_BODIES = {
    "sun": "10", "mercury": "199", "venus": "299", "moon": "301", "mars": "499",
    "jupiter": "599", "saturn": "699", "uranus": "799", "neptune": "899", "pluto": "999",
    "phobos": "401", "deimos": "402", "io": "501", "europa": "502", "ganymede": "503",
    "callisto": "504", "enceladus": "602", "titan": "606", "triton": "801", "charon": "901",
}
_KNOWN_SMALL = {"ceres", "vesta", "pallas", "juno", "eros", "bennu", "ryugu", "apophis", "psyche",
                "halley", "oumuamua", "borisov", "didymos", "itokawa", "hale-bopp", "encke"}
_PREFIX_RE = re.compile(r"^(comet|asteroid|minor planet|dwarf planet|interstellar object)\s+", re.I)
_NUMBERED_COMET_RE = re.compile(r"^(\d+[IPD])(?:/.*)?$", re.I)
_PROVISIONAL_RE = re.compile(r"^([CPDIA]/\d{4} [A-Z]{1,2}\d*)(?:\s.*)?$", re.I)
_NUMBERED_ASTEROID_RE = re.compile(r"^\(?(\d+)\)?\s+[A-Za-z]")
_TARGET_RE = re.compile(r"Target body name:\s*(.+?)\s*\{")


def looks_like_solar_system(name: str) -> bool:
    """Conservative test used in 'auto' mode. '<number> <name>' is deliberately not treated
    as an asteroid here, because star names such as '51 Pegasi' have the same shape."""
    n = name.strip().lower()
    if _PREFIX_RE.match(n):
        return True
    bare = _PREFIX_RE.sub("", name.strip())
    return (n in MAJOR_BODIES or n in _KNOWN_SMALL or n == "earth"
            or bool(_NUMBERED_COMET_RE.match(bare) or _PROVISIONAL_RE.match(bare)))


def candidate_commands(name: str) -> list[str]:
    """Horizons COMMAND strings to try, most specific first."""
    bare = _PREFIX_RE.sub("", name.strip())
    low = bare.lower()
    if low in MAJOR_BODIES:
        return [MAJOR_BODIES[low]]
    m = _NUMBERED_COMET_RE.match(bare)
    if m:
        des = m.group(1).upper()
        return [des, f"DES={des};CAP;NOFRAG"]
    m = _PROVISIONAL_RE.match(bare)
    if m:
        des = m.group(1)
        des = des[0].upper() + des[1:]
        return [f"DES={des};CAP;NOFRAG", f"DES={des};"]
    m = _NUMBERED_ASTEROID_RE.match(bare)
    if m:
        return [f"{m.group(1)};"]
    if bare.isdigit():
        return [f"{bare};"]
    return [f"{bare};", f"{bare};CAP;NOFRAG"]


class HorizonsClient:
    def __init__(self, http: ArchiveClient, api_url: str):
        self.http = http
        self.api_url = api_url

    async def resolve(self, name: str, epoch_utc: str | None = None) -> ResolveResult:
        if name.strip().lower() == "earth":
            return ResolveResult(status="not_found", query_name=name,
                                 message="Earth is the observing site, so it has no sky position.")
        try:
            epoch = parse_utc(epoch_utc) if epoch_utc else datetime.now(timezone.utc)
        except ValueError as exc:
            raise InvalidInputError("epoch_utc must be an ISO-8601 date or datetime.") from exc
        jd = datetime_to_mjd(epoch) + JD_MINUS_MJD
        source = {"name": "JPL Horizons", "url": HORIZONS_HOME}
        last = ResolveResult(status="not_found", query_name=name, sources=[source],
                             message=f"JPL Horizons has no Solar System body matching '{name}'.")
        for command in candidate_commands(name):
            text = await self._query(command, jd)
            result = self._parse(name, text, epoch)
            result.sources = [source]
            numbered = _NUMBERED_ASTEROID_RE.match(_PREFIX_RE.sub("", name.strip()))
            if result.status == "resolved" and numbered:
                # '<number> <name>' was looked up by number: accept only if the name agrees.
                wanted = _PREFIX_RE.sub("", name.strip()).split(None, 1)[1].strip("() ").lower()
                if wanted not in result.object.name.lower():
                    continue
            if result.status == "resolved":
                return result
            if result.status == "ambiguous" or last.status == "not_found":
                last = result
        return last

    async def _query(self, command: str, jd: float) -> str:
        params = {"format": "text", "COMMAND": f"'{command}'", "EPHEM_TYPE": "OBSERVER",
                  "CENTER": "'500@399'", "TLIST": f"'{jd:.5f}'", "QUANTITIES": "'1'",
                  "ANG_FORMAT": "DEG", "CSV_FORMAT": "YES"}
        resp = await self.http.request("GET", self.api_url, params=params, service="JPL Horizons")
        if resp.status_code >= 400:
            raise UpstreamError(f"JPL Horizons rejected the request (HTTP {resp.status_code}).")
        return resp.text

    @staticmethod
    def _parse(name: str, text: str, epoch: datetime) -> ResolveResult:
        if "$$SOE" in text and "$$EOE" in text:
            line = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip().splitlines()[0]
            fields = [f.strip() for f in line.split(",")]
            numbers = []
            for field in fields[1:]:
                try:
                    numbers.append(float(field))
                except ValueError:
                    continue
            if len(numbers) < 2:
                raise UpstreamError("JPL Horizons returned an ephemeris line that could not be parsed.")
            target = _TARGET_RE.search(text)
            epoch_iso = epoch.isoformat(timespec="seconds").replace("+00:00", "Z")
            obj = CelestialObject(
                query_name=name, name=target.group(1) if target else name,
                ra=numbers[0], dec=numbers[1], coordinate_frame="ICRF",
                object_type="solar_system_body", object_type_label="Solar System body",
                catalog_source="JPL Horizons", source_url=HORIZONS_HOME,
                is_solar_system=True, position_time_dependent=True,
                position_epoch_utc=epoch_iso, observer_location="Geocentric (500@399)",
                notes=["Astrometric position for a geocentric observer at the stated epoch only. "
                       "The object moves; SPHEREx observes from low Earth orbit, so parallax of "
                       "nearby bodies can differ slightly."],
            )
            return ResolveResult(status="resolved", query_name=name, object=obj,
                                 message=f"JPL Horizons position of {obj.name} at {epoch_iso}.")
        if re.search(r"Matching small-bodies|Multiple major-bodies match", text):
            rows = []
            for raw in text.splitlines():
                if re.match(r"^\s*-?\d+\s{2,}\S", raw):
                    rows.append({"record": " ".join(raw.split()), "catalog_source": "JPL Horizons"})
            return ResolveResult(status="ambiguous", query_name=name, candidates=rows[:10],
                                 message=f"JPL Horizons lists several bodies matching '{name}'. "
                                         "Please give a designation or number.")
        if re.search(r"No matches found|Cannot find|No such object", text, re.I):
            return ResolveResult(status="not_found", query_name=name,
                                 message=f"JPL Horizons has no Solar System body matching '{name}'.")
        raise UpstreamError("JPL Horizons returned an unexpected response.")
