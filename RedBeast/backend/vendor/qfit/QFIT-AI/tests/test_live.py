"""Live integration tests against the real public services.

    pytest tests/test_live.py --run-live -rs

A test that cannot reach its service is reported as SKIPPED with reason "BLOCKED",
never as passed."""
from __future__ import annotations

import pytest

from app.api.dependencies import Container
from app.config import Settings
from app.utils.errors import UpstreamError, UpstreamUnavailableError

pytestmark = pytest.mark.live
M31 = (10.684708, 41.26875)


@pytest.fixture
async def live():
    container = Container(Settings(_env_file=None, gemini_api_key=None))
    yield container
    await container.aclose()


async def reach(coro):
    """Run a live call; an outage of the external service is BLOCKED (skipped), never passed or failed.
    Outage = unreachable / timed out, or a 5xx server error. A 4xx (the service rejected our query)
    is a real failure and is raised."""
    try:
        return await coro
    except UpstreamUnavailableError as exc:
        pytest.skip(f"BLOCKED: external service unreachable from this machine ({exc.message})")
    except UpstreamError as exc:
        if "server error 5" in exc.message or "HTTP 5" in exc.message:
            pytest.skip(f"BLOCKED: external service outage ({exc.message})")
        raise


async def test_live_irsa_sia_finds_spherex_images_of_m31(live):
    result = await reach(live.observations.search_observations(ra=M31[0], dec=M31[1], limit=5))
    assert result["spherex_available"] is True and result["total"] > 0
    first = result["observations"][0]
    assert first["access_url"].startswith("https://irsa.ipac.caltech.edu/ibe/data/spherex/")
    assert first["detector"] in range(1, 7) and 0.7 < first["wavelength_min_um"] < 5.1


async def test_live_irsa_all_sky_cube_tile(live):
    tiles = await reach(live.spherex.find_cube_tiles(M31[0], M31[1], 0.003))
    assert tiles and tiles[0].product_kind == "all_sky_cube" and tiles[0].access_url.endswith("_cube.fits")


async def test_live_irsa_tap_metadata_roundtrip(live):
    found = await reach(live.observations.search_observations(ra=M31[0], dec=M31[1], limit=1))
    observation_id = found["observations"][0]["observation_id"]
    live.spherex._seen.clear()                               # force the TAP path
    products = await reach(live.spherex.get_products_by_id(observation_id))
    assert products and products[0].metadata_source == "IRSA TAP"
    assert products[0].access_url == found["observations"][0]["access_url"]


async def test_live_irsa_download_reference_is_real(live):
    found = await reach(live.retrieval.image_products(ra=M31[0], dec=M31[1], limit=1, verify=True))
    assert found["image_products"][0]["download_check"]["verified"] is True


async def test_live_spectral_sample_from_cutout(live):
    result = await reach(live.retrieval.spectral_products(ra=M31[0], dec=M31[1], extract_samples=True, max_samples=1))
    sample = result["samples"][0]
    assert sample["ok"] is True, sample
    assert sample["surface_brightness_unit"] == "MJy/sr" and 0.7 < sample["wavelength_um"] < 5.1


async def test_live_observation_periods(live):
    result = await reach(live.observations.observation_periods(ra=M31[0], dec=M31[1]))
    assert result["period_count"] >= 1 and result["periods"][0]["start_utc"] >= "2025-04"


async def test_live_simbad_resolves_andromeda(live):
    result = await reach(live.resolver.resolve("Andromeda Galaxy"))
    assert result.status == "resolved"
    assert abs(result.object.ra - M31[0]) < 0.01 and abs(result.object.dec - M31[1]) < 0.01
    if result.object.catalog_source == "CDS Sesame":       # the outage fallback worked; SIMBAD itself did not
        assert "SIMBAD was unreachable" in result.message
        pytest.skip("BLOCKED: SIMBAD unreachable; resolved through the CDS Sesame fallback instead")
    assert result.object.catalog_source == "SIMBAD"


async def test_live_simbad_cone_search_brown_dwarfs(live):
    result = await reach(live.search.objects_near(56.75, 24.12, 0.5, "brown dwarf", 5))
    assert all(o["object_type"] for o in result["objects"])


async def test_live_horizons_mars_and_3i_atlas(live):
    mars = await reach(live.resolver.resolve("Mars", epoch_utc="2026-11-15T00:00:00Z"))
    assert mars.status == "resolved" and abs(mars.object.ra - 147.88854) < 0.01
    comet = await reach(live.resolver.resolve("Comet 3I/ATLAS"))
    assert comet.status == "resolved" and "ATLAS" in comet.object.name


async def test_live_png_preview_of_a_real_cutout(live):
    found = await reach(live.retrieval.image_products(ra=M31[0], dec=M31[1], limit=1, cutout_size_deg=0.1))
    item = found["image_products"][0]
    try:
        png, meta = await live.previews.preview(item["observation_id"], ra=M31[0], dec=M31[1], size_deg=0.1)
    except UpstreamError as exc:          # IRSA's cutout service answering 5xx is an outage, not a pass
        pytest.skip(f"BLOCKED: IRSA cutout service ({exc.message})")
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and meta["width"] > 10 and meta["height"] > 10
    centre_ra = sum(c[0] for c in list(meta["corners_radec"].values())[:4]) / 4
    assert abs(centre_ra - M31[0]) < 0.1 and meta["scale_range"]["unit"] == "MJy/sr"
