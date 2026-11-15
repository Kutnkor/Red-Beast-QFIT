"""PNG previews of FITS cutouts. A synthetic FITS file with known content checks the vertical
flip, the transparency of blank pixels, the stretch and the sky corners; the endpoint tests use
the fake archive."""
from __future__ import annotations

import io

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.services.preview_service import render_png
from app.utils.errors import InvalidInputError, UpstreamError

OBS = "spherex_dr1_deep:2025W18_1B_0001_1:D1"     # served by the fake TAP archive in conftest


def synthetic_fits(nx: int = 40, ny: int = 30) -> bytes:
    """North-up TAN image at RA 10, Dec 41: brightness rises with the row number, one blank block."""
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [10.0, 41.0]
    w.wcs.crpix = [(nx + 1) / 2, (ny + 1) / 2]
    w.wcs.cdelt = [-6.15 / 3600, 6.15 / 3600]          # east to the left, north up
    data = np.tile(np.arange(ny, dtype=np.float32)[:, None], (1, nx))
    data[0:5, 0:5] = np.nan                             # bottom-left corner of the FITS image
    header = w.to_header()
    header["BUNIT"] = "MJy / sr"
    hdul = fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(data, header=header, name="IMAGE")])
    out = io.BytesIO()
    hdul.writeto(out)
    return out.getvalue()


def test_render_png_flips_masks_and_places_corners():
    png, meta = render_png(synthetic_fits(), stretch="linear", low_pct=0, high_pct=100)
    image = Image.open(io.BytesIO(png))
    assert image.mode == "LA" and image.size == (40, 30) and (meta["width"], meta["height"]) == (40, 30)
    grey, alpha = np.asarray(image)[..., 0], np.asarray(image)[..., 1]
    assert grey[0, 20] == 255 and grey[-1, 20] == 0          # FITS top row (brightest) is the PNG top row
    assert alpha[-1, 0] == 0 and alpha[-5, 4] == 0 and alpha[0, 0] == 255   # blank block -> transparent, bottom-left
    assert meta["blank_fraction"] == pytest.approx(25 / 1200, abs=1e-4)
    assert meta["scale_range"]["unit"] == "MJy/sr" and meta["scale_range"]["low"] == 0.0
    c = meta["corners_radec"]
    assert c["top_left"][1] > c["bottom_left"][1] and c["top_left"][0] > c["top_right"][0]   # north up, east left
    assert c["top_left"][0] == pytest.approx(10 + 20 * 6.15 / 3600 / np.cos(np.radians(41)), abs=2e-3)
    assert "not a measurement" in meta["note"]


def test_render_png_stretches_and_errors():
    linear, _ = render_png(synthetic_fits(), stretch="linear")
    asinh, _ = render_png(synthetic_fits(), stretch="asinh")
    mid = lambda png: np.asarray(Image.open(io.BytesIO(png)))[15, 20, 0]
    assert mid(asinh) > mid(linear)                          # asinh lifts the faint end
    with pytest.raises(InvalidInputError):
        render_png(synthetic_fits(), stretch="rainbow")
    with pytest.raises(InvalidInputError):
        render_png(synthetic_fits(), low_pct=90, high_pct=10)
    with pytest.raises(UpstreamError):
        render_png(b"not a fits file at all" * 200)
    no_image = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU()]).writeto(no_image)
    with pytest.raises(UpstreamError, match="no IMAGE"):
        render_png(no_image.getvalue())


def test_preview_endpoints_and_cache(settings, container, monkeypatch):
    downloads = []

    async def fake_download(url, max_bytes, **_):
        downloads.append(url)
        return synthetic_fits()
    monkeypatch.setattr(container.archive, "download_bytes", fake_download)
    with TestClient(create_app(settings, container)) as client:
        params = {"observation_id": OBS, "ra": 10.0, "dec": 41.0, "size_deg": 0.1}
        png = client.get("/api/v1/images/preview", params=params)
        info = client.get("/api/v1/images/preview/info", params=params).json()
        bad = client.get("/api/v1/images/preview", params={**params, "size_deg": 5})
        lonely = client.get("/api/v1/images/preview", params={"observation_id": OBS, "ra": 10.0})
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(png.content)).size == (40, 30)
    assert len(downloads) == 1 and "?center=10.0000000,41.0000000&size=0.1" in downloads[0]   # second call cached
    preview = info["data"]["preview"]
    assert info["success"] and preview["png_url"].startswith("/api/v1/images/preview?observation_id=")
    assert preview["detector"] == 1 and set(preview["corners_radec"]) >= {"top_left", "bottom_right"}
    assert info["media"][0]["media_type"] == "png_preview" and "not a measurement" in info["uncertainty"][0]
    assert bad.status_code == 422 and lonely.status_code == 422


def test_image_search_results_carry_a_preview_url(client):
    body = client.post("/api/v1/images/search", json={"ra": 127.7, "dec": -39.2, "limit": 2}).json()
    item = body["data"]["image_products"][0]
    assert item["preview_url"].startswith("/api/v1/images/preview?observation_id=")
    assert "ra=127.7000000" in item["preview_url"] and "size_deg=0.5" in item["preview_url"]
    assert body["actions"][-1]["payload"]["products"][0]["preview_url"] == item["preview_url"]
    assert body["media"][0]["preview_url"] == item["preview_url"]
