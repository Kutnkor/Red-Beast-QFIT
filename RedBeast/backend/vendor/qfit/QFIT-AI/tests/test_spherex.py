"""SPHEREx archive layer (IRSA SIA2 / TAP) - deterministic unit tests."""
from __future__ import annotations

import io
from urllib.parse import parse_qs

import numpy as np
import pytest

from app.astronomy.archive_client import parse_csv_table
from app.astronomy.spherex_client import cutout_url, product_from_sia, read_pixel_sample
from app.services.observation_service import group_periods
from app.utils.errors import InvalidInputError, NotFoundError, UpstreamError
from app.utils.validation import parse_observation_id
from tests.conftest import IMAGE_ROWS


def test_sia_row_is_mapped_without_inventing_values():
    p = product_from_sia(IMAGE_ROWS[3])
    assert p.observation_id == "spherex_qr3:2026W21_1A_0491_2:D4"
    assert p.detector == 4 and p.bandpass == "SPHEREx-D4" and p.release == "QR3"
    assert p.wavelength_min_um == pytest.approx(2.4027) and p.wavelength_max_um == pytest.approx(3.8473)
    assert p.t_min_mjd == pytest.approx(61181.214941) and p.t_min_utc.startswith("2026-05-21T05:09")
    assert p.access_url == IMAGE_ROWS[3]["access_url"]          # verbatim from the archive
    assert p.cloud_access["aws"]["bucket_name"] == "nasa-irsa-spherex"
    assert p.exposure_s == pytest.approx(113.5826) and p.est_size_kb == 58482


def test_cutout_url_follows_irsa_syntax():
    url = cutout_url("https://irsa.ipac.caltech.edu/ibe/x.fits", 337.8783221, -5.1891588, 0.1)
    assert url == "https://irsa.ipac.caltech.edu/ibe/x.fits?center=337.8783221,-5.1891588&size=0.1"


async def test_coordinate_search_builds_documented_sia_query(container, fake_archive):
    products, truncated = await container.spherex.search_products(127.69444, -39.1776, 0.01)
    query = parse_qs(fake_archive.requests[0].url.query.decode())
    assert fake_archive.requests[0].url.path == "/SIA"
    assert query["POS"] == ["circle 127.6944400 -39.1776000 0.0100000"]
    assert query["COLLECTION"] == ["spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep"]
    assert query["RESPONSEFORMAT"] == ["CSV"]
    assert len(products) == 6 and not truncated
    assert [p.t_min_mjd for p in products] == sorted(p.t_min_mjd for p in products)


async def test_archive_metadata_is_cached(container, fake_archive):
    await container.spherex.search_products(10.0, 20.0, 0.01)
    await container.spherex.search_products(10.0, 20.0, 0.01)
    assert len(fake_archive.requests) == 1


async def test_missing_data_is_an_explicit_no_data_result(container):
    result = await container.observations.search_observations(ra=0.0, dec=-85.0)
    assert result["status"] == "no_data" and result["spherex_available"] is False
    assert result["observations"] == [] and result["total"] == 0 and result["possible_reasons"]


async def test_observation_search_pagination_and_filters(container):
    page = await container.observations.search_observations(ra=127.7, dec=-39.2, limit=2, offset=4)
    assert page["total"] == 6 and page["returned"] == 2 and page["has_more"] is False
    only_d4 = await container.observations.search_observations(ra=127.7, dec=-39.2, detector=4)
    assert {o["detector"] for o in only_d4["observations"]} == {4} and only_d4["total"] == 2
    with pytest.raises(InvalidInputError):
        await container.observations.search_observations(ra=127.7, dec=-39.2, start_utc="2026-06-01", end_utc="2026-01-01")


async def test_transient_archive_failure_is_retried(container, fake_archive):
    fake_archive.fail_next = [503]
    products, _ = await container.spherex.search_products(127.7, -39.2, 0.01)
    assert len(products) == 6 and len(fake_archive.requests) == 2


async def test_persistent_archive_failure_becomes_upstream_error(container, fake_archive):
    fake_archive.fail_next = [503, 503, 503]
    with pytest.raises(UpstreamError):
        await container.spherex.search_products(127.7, -39.2, 0.01)


async def test_archive_error_document_is_not_treated_as_empty(container):
    with pytest.raises(UpstreamError, match="bad POS"):
        await container.spherex.search_products(350.0, 10.0, 0.01)


def test_csv_parser_turns_blank_cells_into_none():
    assert parse_csv_table("a,b\n1,\n", "x") == [{"a": "1", "b": None}]
    assert parse_csv_table("", "x") == [] and parse_csv_table("a,b\n", "x") == []


async def test_observation_metadata_by_id_uses_tap(container, fake_archive):
    products = await container.spherex.get_products_by_id("spherex_dr1_deep:2025W18_1B_0001_1:D1")
    adql = parse_qs(fake_archive.requests[-1].url.query.decode())["QUERY"][0]
    assert "FROM spherex.plane p JOIN spherex.artifact a ON a.planeid = p.planeid" in adql
    assert "p.obs_publisher_did = 'ivo://irsa.ipac/spherex_dr1_deep?2025W18_1B_0001_1/D1'" in adql
    p = products[0]
    assert p.metadata_source == "IRSA TAP" and p.detector == 1 and p.est_size_kb == 63860
    assert p.access_url.startswith("https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W18_1B/")
    assert p.center_ra == pytest.approx(276.26389, abs=1e-4) and p.center_dec == pytest.approx(64.82396, abs=1e-4)


async def test_observation_metadata_reuses_recent_search_results(container, fake_archive):
    await container.spherex.search_products(127.7, -39.2, 0.01)
    before = len(fake_archive.requests)
    products = await container.spherex.get_products_by_id("spherex_qr3:2026W21_1A_0491_2:D4")
    assert products[0].metadata_source == "IRSA SIA2" and len(fake_archive.requests) == before


async def test_unknown_observation_id_is_not_found(container):
    with pytest.raises(NotFoundError):
        await container.observations.get_observation("spherex_qr3:2099W01_1A_0001_1:D1")


@pytest.mark.parametrize("bad", ["a:b:c:d", "spherex_qr3:x' OR 1=1:D1", "evil:2026W21_1A_0491_2:D4", ""])
def test_malformed_observation_ids_are_rejected(bad):
    with pytest.raises(InvalidInputError):
        parse_observation_id(bad)


async def test_observation_periods_group_by_revisit(container):
    result = await container.observations.observation_periods(ra=127.7, dec=-39.2)
    assert result["period_count"] == 2
    first, second = result["periods"]
    assert first["start_utc"].startswith("2025-11-11") and second["start_utc"].startswith("2026-05-21")
    assert first["exposures"] == 2 and second["detectors"] == [1, 4]


def test_group_periods_handles_empty_input():
    assert group_periods([], 20) == []


async def test_image_retrieval_returns_archive_urls_and_verifies_on_request(container, fake_archive):
    result = await container.retrieval.image_products(ra=127.7, dec=-39.2, limit=3, verify=True)
    assert result["returned"] == 3 and result["total_available"] == 6
    for item in result["image_products"]:
        assert item["cutout_url"] == f"{item['access_url']}?center=127.7000000,-39.2000000&size=0.1"
        assert item["download_check"] == {"verified": True, "http_status": 200, "content_length": 59885568}
    assert sum(r.method == "HEAD" for r in fake_archive.requests) == 3
    unverified = await container.retrieval.image_products(ra=127.7, dec=-39.2, limit=1)
    assert unverified["image_products"][0]["download_check"] == {"verified": None}


async def test_spectral_products_distinguish_cube_from_single_band_images(container):
    result = await container.retrieval.spectral_products(ra=127.7, dec=-39.2)
    cube = result["spectral_products"][0]
    assert cube["product_kind"] == "all_sky_cube" and cube["spectral_channels"] == 102
    assert cube["observation_id"] == "spherex_dr1_cube:hips5_cube-hips_20261026:677"
    coverage = result["spectral_image_coverage"]
    assert [b["detector"] for b in coverage["bands"]] == [1, 4, 6]
    assert coverage["detectors_missing"] == [2, 3, 5]       # never assume a full 102-band spectrum
    assert result["samples"] == []


def test_pixel_sample_reads_image_extensions():
    from astropy.io import fits
    from astropy.wcs import WCS
    wcs = WCS(naxis=2)
    wcs.wcs.ctype, wcs.wcs.crval, wcs.wcs.crpix = ["RA---TAN", "DEC--TAN"], [150.0, 2.0], [5.5, 5.5]
    wcs.wcs.cdelt = [-6.15 / 3600, 6.15 / 3600]
    header = wcs.to_header()
    header["BUNIT"] = "MJy/sr"
    image = np.arange(100, dtype="float32").reshape(10, 10)
    hdul = fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(image, header, name="IMAGE"),
                         fits.ImageHDU(np.zeros((10, 10), "int32"), name="FLAGS"),
                         fits.ImageHDU(np.full((10, 10), 0.25, "float32"), name="VARIANCE"),
                         fits.ImageHDU(np.full((10, 10), 0.4, "float32"), name="ZODI")])
    buffer = io.BytesIO()
    hdul.writeto(buffer)
    sample = read_pixel_sample(buffer.getvalue(), 150.0, 2.0)
    xi, yi = sample["pixel_xy"]
    assert sample["surface_brightness"] == pytest.approx(float(image[yi, xi]))
    assert sample["surface_brightness_unit"] == "MJy/sr" and sample["variance"] == pytest.approx(0.25)
    assert sample["flags"] == 0 and sample["wavelength_um"] is None and "wavelength_note" in sample
    with pytest.raises(ValueError):
        read_pixel_sample(buffer.getvalue(), 10.0, -60.0)
