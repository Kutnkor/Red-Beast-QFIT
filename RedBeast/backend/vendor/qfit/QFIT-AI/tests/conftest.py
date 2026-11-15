"""Shared fixtures. Unit tests never touch the network: IRSA and Horizons are served
by an httpx MockTransport, SIMBAD/Sesame by an ObjectResolver subclass, and the LLM by
a scripted provider. The archive fixtures reuse real rows captured from IRSA."""
from __future__ import annotations

import csv
import io
import os
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai.llm_provider import LLMTurn, ToolCall
from app.api.dependencies import Container
from app.astronomy.object_resolver import ObjectResolver
from app.config import Settings
from app.main import create_app


def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", default=False,
                     help="run tests against the real IRSA / SIMBAD / Horizons / Gemini services")


def pytest_collection_modifyitems(config, items):
    run_live = config.getoption("--run-live") or os.getenv("QFIT_RUN_LIVE") == "1"
    for item in items:
        if "live" in item.keywords and not run_live:
            item.add_marker(pytest.mark.skip(reason="LIVE test: enable with --run-live"))
        if "requires_credentials" in item.keywords and not os.getenv("GEMINI_API_KEY"):
            item.add_marker(pytest.mark.skip(reason="NEEDS CREDENTIALS: set GEMINI_API_KEY"))


SIA_COLUMNS = ["s_ra", "s_dec", "facility_name", "instrument_name", "dataproduct_subtype", "calib_level",
               "dataproduct_type", "energy_bandpassname", "energy_emband", "obs_id", "s_resolution",
               "em_min", "em_max", "em_res_power", "proposal_title", "access_url", "access_format",
               "access_estsize", "t_exptime", "s_region", "obs_collection", "obs_intent", "algorithm_name",
               "target_name", "obs_release_date", "s_xel1", "s_xel2", "s_pixel_scale", "t_min", "t_max",
               "obs_publisher_did", "s_fov", "cloud_access", "upload_row_id"]
BASE = "https://irsa.ipac.caltech.edu"


def sia_row(obs_id: str, detector: int, t_min: float, collection: str = "spherex_qr3") -> dict[str, str]:
    em = {1: ("7.45500e-07", "1.11670e-06", "39.1"), 4: ("2.40270e-06", "3.84730e-06", "34.9"),
          6: ("4.42000e-06", "5.00960e-06", "128.0")}[detector]
    period = obs_id.rsplit("_", 2)[0]
    rel = collection.split("_")[1]
    path = f"ibe/data/spherex/{rel}/level2/{period}/l2b-v27-2026-268/{detector}/level2_{obs_id}D{detector}_spx_l2b-v27-2026-268.fits"
    return {"s_ra": "127.87816174068881", "s_dec": "-41.028582266007454", "facility_name": "SPHEREx",
            "instrument_name": "SPHEREx", "dataproduct_subtype": "science", "calib_level": "2",
            "dataproduct_type": "image", "energy_bandpassname": f"SPHEREx-D{detector}",
            "energy_emband": "Infrared", "obs_id": obs_id, "s_resolution": "3.075000", "em_min": em[0],
            "em_max": em[1], "em_res_power": em[2], "proposal_title": "SPHEREx LVF Survey Data",
            "access_url": f"{BASE}/{path}", "access_format": "image/fits", "access_estsize": "58482",
            "t_exptime": "113.582600", "s_region": "POLYGON ICRS 127.2 -38.6 131.0 -40.4 128.5 -43.4 124.5 -41.5 127.2 -38.6",
            "obs_collection": collection, "obs_intent": "science", "algorithm_name": "exposure",
            "target_name": "SPS_134067_S34", "obs_release_date": "2026-10-10 15:57:41", "s_xel1": "2040",
            "s_xel2": "2040", "s_pixel_scale": "6.150", "t_min": f"{t_min:.6f}", "t_max": f"{t_min + 0.001332:.6f}",
            "obs_publisher_did": f"ivo://irsa.ipac/{collection}?{obs_id}/D{detector}", "s_fov": "3.485e+00",
            "cloud_access": '{"aws": {"bucket_name": "nasa-irsa-spherex", "key":"' + path.removeprefix("ibe/data/spherex/") + '", "region": "us-east-1"}}',
            "upload_row_id": "1"}


CUBE_ROW = {**sia_row("x_y_0001_1", 1, 60789.848), "dataproduct_type": "cube", "calib_level": "3",
            "energy_bandpassname": "SPHEREx", "obs_id": "hips5_cube-hips_20261026", "em_min": "7.45500e-07",
            "em_max": "5.00960e-06", "em_res_power": "", "t_exptime": "", "obs_collection": "spherex_dr1_cube",
            "access_url": f"{BASE}/ibe/data/spherex/dr1/hips5_cube/hips_20261026/Norder5/Dir0/Npix677_cube.fits",
            "access_estsize": "320910", "t_max": "61174.472900", "s_fov": "1.832e+00",
            "obs_publisher_did": "ivo://irsa.ipac/spherex_dr1_cube?hips5_cube-hips_20261026/677",
            "algorithm_name": "mosaic", "target_name": ""}

# Two visits about six months apart, as SPHEREx revisits the sky.
IMAGE_ROWS = [sia_row("2025W47_1A_0100_1", 1, 60990.10), sia_row("2025W47_1A_0100_1", 4, 60990.10),
              sia_row("2025W47_1A_0101_2", 6, 60990.20), sia_row("2026W21_1A_0491_2", 4, 61181.214941),
              sia_row("2026W21_1A_0491_2", 1, 61181.214941), sia_row("2026W21_1A_0480_4", 1, 61181.148464)]


def to_csv(rows: list[dict[str, str]], columns: list[str] = SIA_COLUMNS) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


TAP_COLUMNS = ["obs_publisher_did", "productid", "calibrationlevel", "dataproducttype", "energy_bounds_lower",
               "energy_bounds_upper", "energy_resolvingpower", "energy_bandpassname", "time_bounds_lower",
               "time_bounds_upper", "time_exposure", "position_samplesize", "provenance_name",
               "provenance_version", "datarelease", "pt", "uri", "contenttype", "contentlength", "contentchecksum"]
TAP_ROW = {"obs_publisher_did": "ivo://irsa.ipac/spherex_dr1_deep?2025W18_1B_0001_1/D1", "productid": "D1",
           "calibrationlevel": "2", "dataproducttype": "image", "energy_bounds_lower": "7.45500e-07",
           "energy_bounds_upper": "1.11670e-06", "energy_resolvingpower": "39.100000",
           "energy_bandpassname": "SPHEREx-D1", "time_bounds_lower": "60793.541849",
           "time_bounds_upper": "60793.543181", "time_exposure": "113.582600", "position_samplesize": "6.150000",
           "provenance_name": "SPHEREx SSDC Level 1-2 Quick-Release Pipeline", "provenance_version": "7.0.5",
           "datarelease": "2026-09-27 23:59:28", "pt": "0101000020E6100000307DD76E1CEF54C0B5FB69CABB345040",
           "uri": "ibe/data/spherex/dr1/level2/2025W18_1B/l2b-v27-2026-196/1/level2_2025W18_1B_0001_1D1_spx_l2b-v27-2026-196.fits",
           "contenttype": "image/fits", "contentlength": "65393280", "contentchecksum": "md5:ba0cb5d912601e6ccb45b96245be6234"}

HORIZONS_MARS = """*******************************************************************************
Ephemeris / API_USER Sat Nov 14 10:00:00 2026 Pasadena, USA      / Horizons
*******************************************************************************
Target body name: Mars (499)                      {source: mar099}
Center body name: Earth (399)                     {source: DE441}
*******************************************************************************
 Date__(UT)__HR:MN:SC.fff, , , R.A._(ICRF), DEC_(ICRF),
**************************************************
$$SOE
 2026-Nov-15 00:00:00.000, , ,   147.88854,   15.00509,
$$EOE
*******************************************************************************
"""
HORIZONS_AMBIGUOUS = """*******************************************************************************
JPL/DASTCOM            Small-body Index Search Results     2026-Nov-14 10:00:00

 Matching small-bodies:

    Record #  Epoch-yr  Primary Desig  >MATCH NAME<
    --------  --------  -------------  -------------------------
    90000030    1986    1P             Halley
    90000031    1968    1P             Halley

 (2 matches. To SELECT, enter record # (integer), followed by semi-colon.)
*******************************************************************************
"""
HORIZONS_NONE = "No matches found.\n"


class FakeArchive:
    """Stands in for IRSA and JPL Horizons; records every request it receives."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.fail_next: list[int] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_next:
            return httpx.Response(self.fail_next.pop(0), text="temporarily unavailable")
        path, query = request.url.path, parse_qs(request.url.query.decode())
        if path == "/SIA":
            collections = query.get("COLLECTION", [])
            _, ra, dec, _ = query["POS"][0].split()
            if float(dec) < -80:                       # an uncovered region
                return httpx.Response(200, text=to_csv([]))
            if float(ra) > 300:                        # the archive answers with an error document
                return httpx.Response(200, text='<VOTABLE><INFO name="QUERY_STATUS" value="ERROR">bad POS</INFO></VOTABLE>')
            rows = [CUBE_ROW] if collections == ["spherex_dr1_cube"] else \
                [r for r in IMAGE_ROWS if r["obs_collection"] in collections]
            return httpx.Response(200, text=to_csv(rows[: int(query.get("MAXREC", ["99999"])[0])]))
        if path == "/TAP/sync":
            adql = query["QUERY"][0]
            return httpx.Response(200, text=to_csv([TAP_ROW] if "2025W18_1B_0001_1" in adql else [], TAP_COLUMNS))
        if path.endswith("horizons.api"):
            command = query["COMMAND"][0].strip("'")
            if command in ("499", "3I"):
                return httpx.Response(200, text=HORIZONS_MARS)
            return httpx.Response(200, text=HORIZONS_AMBIGUOUS if "Halley" in command or "1P" in command else HORIZONS_NONE)
        if path.startswith("/ibe/data/"):
            return httpx.Response(200, headers={"Content-Length": "59885568"})
        return httpx.Response(404, text="not found")


M31 = {"main_id": "M  31", "ra": 10.684708, "dec": 41.26875, "otype": "G", "coo_bibcode": "2006AJ....131.1163S",
       "matched_id": "NAME Andromeda Galaxy"}


class FakeResolver(ObjectResolver):
    """ObjectResolver with the CDS network seams replaced by canned catalog answers."""

    def _simbad_by_name(self, name: str) -> list[dict[str, Any]]:
        key = name.lower()
        if key in ("m31", "andromeda galaxy", "m 31"):
            return [M31]
        if key == "twins":
            return [{**M31, "main_id": "Twin A"}, {**M31, "main_id": "Twin B", "ra": 11.0}]
        if key == "simbad down":
            raise ConnectionError("network unreachable")
        return []

    def _simbad_name_candidates(self, name: str, limit: int) -> list[dict[str, Any]]:
        if name.lower() == "pinwheel":
            return [{"main_id": "M 101", "ra": 210.80227, "dec": 54.34895, "otype": "G", "matched_id": "NAME Pinwheel Galaxy"},
                    {"main_id": "M  99", "ra": 184.70677, "dec": 14.41649, "otype": "G", "matched_id": "NAME Virgo Pinwheel"}]
        return []

    def _simbad_cone(self, ra, dec, radius_deg, otype, limit):
        self.last_cone = (ra, dec, radius_deg, otype, limit)
        return [{"main_id": "Teide 1", "ra": ra + 0.01, "dec": dec, "otype": "BD*"},
                {"main_id": "Calar 3", "ra": ra, "dec": dec + 0.001, "otype": "BD*"}]

    def _sesame(self, name: str):
        return (201.365, -43.019) if name.lower() == "centaurus a" else None


class ScriptedProvider:
    """LLM stand-in: replays prepared turns and records what it was sent."""
    name, model = "scripted", "scripted-test-model"

    def __init__(self, turns: list[LLMTurn]):
        self.turns, self.calls = list(turns), []

    async def generate(self, *, system, messages, tools):
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "tools": tools})
        return self.turns.pop(0)


def call(tool: str, /, **args: Any) -> LLMTurn:
    return LLMTurn(text="", tool_calls=[ToolCall(name=tool, args=args, id=f"call-{tool}")])


@pytest.fixture
def settings(tmp_path) -> Settings:
    # qfit_data_dir points at a temporary folder: tests never write the real candidate log.
    return Settings(_env_file=None, gemini_api_key=None, http_max_retries=1, chat_rate_limit_per_minute=0,
                    max_request_body_bytes=4096, qfit_data_dir=str(tmp_path / "data"))


@pytest.fixture
def fake_archive() -> FakeArchive:
    return FakeArchive()


@pytest.fixture
def make_container(settings, fake_archive):
    def build(provider=None, **overrides) -> Container:
        cfg = settings.model_copy(update=overrides)
        container = Container(cfg, transport=httpx.MockTransport(fake_archive), provider=provider)
        container.resolver = FakeResolver(container.horizons, timeout=5, cache_ttl=0)
        container.search.resolver = container.resolver
        return container
    return build


@pytest.fixture
def container(make_container) -> Container:
    return make_container()


@pytest.fixture
def client(settings, container):
    with TestClient(create_app(settings, container)) as test_client:
        yield test_client
