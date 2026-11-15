"""PNG previews of SPHEREx spectral images, for browsers and Three.js textures.

A browser cannot display FITS. This service downloads an IRSA cutout of one spectral image,
scales its IMAGE extension (surface brightness, MJy/sr) to 8-bit grey and returns a PNG plus the
sky position of the PNG's four corners, so a client can place the texture on the sky.

What the picture is, and is not: one detector band, one exposure, raw surface brightness with
zodiacal light not subtracted, wavelength varying across the image. A display stretch is applied;
pixel brightness in the PNG is not a measurement. The metadata says so.
"""
from __future__ import annotations

import asyncio
import io
from typing import Any
from urllib.parse import urlencode

from app.astronomy.spherex_client import cutout_url
from app.utils.cache import TTLCache
from app.utils.errors import InvalidInputError, UpstreamError

STRETCHES = ("asinh", "log", "linear")
MAX_SIZE_DEG = 1.0
DEFAULT_SIZE_DEG = 0.5
PREVIEW_SIZE_DEG = DEFAULT_SIZE_DEG
PREVIEW_NOTE = ("Display image: one SPHEREx detector band from one exposure, wavelength varying across the "
                "image, raw surface brightness (MJy/sr) with zodiacal light not subtracted, scaled for viewing. "
                "Brightness in the PNG is not a measurement; use the FITS file for values.")


def render_png(fits_bytes: bytes, *, stretch: str = "asinh", low_pct: float = 1.0,
               high_pct: float = 99.5) -> tuple[bytes, dict[str, Any]]:
    """IMAGE extension of a SPHEREx (cutout) FITS file -> grey+alpha PNG and metadata."""
    import numpy as np
    from astropy import log as astropy_log
    from astropy.io import fits
    from astropy.wcs import WCS
    from PIL import Image

    if stretch not in STRETCHES:
        raise InvalidInputError(f"stretch must be one of: {', '.join(STRETCHES)}.")
    if not 0 <= low_pct < high_pct <= 100:
        raise InvalidInputError("Percentiles must satisfy 0 <= low_pct < high_pct <= 100.")
    astropy_log.setLevel("WARNING")       # SPHEREx headers trigger a long INFO note about SIP terms
    try:
        with fits.open(io.BytesIO(fits_bytes), memmap=False) as hdul:
            if "IMAGE" not in hdul:
                raise UpstreamError("The archive file has no IMAGE extension.")
            header = hdul["IMAGE"].header
            data = np.asarray(hdul["IMAGE"].data, dtype=np.float64)
            wcs = WCS(header)
    except OSError as exc:
        raise UpstreamError("The archive returned a file that is not readable FITS.") from exc
    if data.ndim != 2:
        raise UpstreamError("The IMAGE extension is not a 2-D image.")
    finite = np.isfinite(data)
    if finite.sum() < 4:
        raise UpstreamError("The cutout contains no valid pixels.")
    low, high = (float(v) for v in np.percentile(data[finite], [low_pct, high_pct]))
    if high <= low:
        high = low + 1e-9
    x = np.clip((np.where(finite, data, low) - low) / (high - low), 0.0, 1.0)
    if stretch == "asinh":
        x = np.arcsinh(10.0 * x) / np.arcsinh(10.0)
    elif stretch == "log":
        x = np.log10(1.0 + 999.0 * x) / 3.0
    grey = np.round(x * 255.0).astype(np.uint8)
    alpha = np.where(finite, 255, 0).astype(np.uint8)
    # FITS stores the first row at the bottom, PNG at the top.
    pixels = np.flipud(np.dstack([grey, alpha]))
    out = io.BytesIO()
    Image.fromarray(pixels, mode="LA").save(out, format="PNG", optimize=True)

    ny, nx = data.shape
    # Outer pixel edges (0-based pixel centres, so edges at -0.5 and n-0.5), in PNG order.
    corners_px = [(-0.5, ny - 0.5), (nx - 0.5, ny - 0.5), (nx - 0.5, -0.5), (-0.5, -0.5)]
    corners = []
    for px, py in corners_px:
        world = wcs.pixel_to_world(px, py)
        corners.append([round(float(world.ra.deg), 6), round(float(world.dec.deg), 6)])
    unit = "".join(str(header.get("BUNIT", "MJy/sr")).split())
    meta = {
        "width": nx, "height": ny, "stretch": stretch,
        "scale_range": {"low": low, "high": high, "unit": unit, "percentiles": [low_pct, high_pct]},
        "blank_fraction": round(1 - float(finite.mean()), 4),
        "corners_radec": {"top_left": corners[0], "top_right": corners[1], "bottom_right": corners[2],
                          "bottom_left": corners[3], "frame": "ICRS"},
        "note": PREVIEW_NOTE,
    }
    return out.getvalue(), meta


def preview_path(observation_id: str, ra: float | None, dec: float | None, size_deg: float,
                 stretch: str = "asinh") -> str:
    """Relative URL of the PNG preview, for API responses."""
    query = {"observation_id": observation_id, "size_deg": f"{size_deg:g}", "stretch": stretch}
    if ra is not None and dec is not None:
        query.update(ra=f"{ra:.7f}", dec=f"{dec:.7f}")
    return "/api/v1/images/preview?" + urlencode(query)


class PreviewService:
    def __init__(self, observations, archive, max_bytes: int, cache_ttl: float = 3600):
        self.observations = observations
        self.archive = archive
        self.max_bytes = max_bytes
        self.cache = TTLCache(cache_ttl, max_entries=64)

    async def preview(self, observation_id: str, *, ra: float | None = None, dec: float | None = None,
                      size_deg: float = DEFAULT_SIZE_DEG, stretch: str = "asinh", low_pct: float = 1.0,
                      high_pct: float = 99.5) -> tuple[bytes, dict[str, Any]]:
        if not 0 < size_deg <= MAX_SIZE_DEG:
            raise InvalidInputError(f"size_deg must be within (0, {MAX_SIZE_DEG:g}] degrees "
                                    "(a full image is about 3.5 deg and 70 MB).")
        if (ra is None) != (dec is None):
            raise InvalidInputError("ra and dec must be given together.")
        key = (observation_id, ra, dec, size_deg, stretch, low_pct, high_pct)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        found = await self.observations.get_observation(observation_id, ra, dec)
        product = next((p for p in found["products"] if p.get("product_kind") == "spectral_image"
                        and p.get("access_url")), None)
        if product is None:
            raise InvalidInputError("Previews exist only for SPHEREx spectral images, not for this product.")
        centre_ra = ra if ra is not None else product.get("center_ra")
        centre_dec = dec if dec is not None else product.get("center_dec")
        if centre_ra is None or centre_dec is None:
            raise InvalidInputError("Give ra and dec: the archive record has no image centre.")
        url = cutout_url(product["access_url"], centre_ra, centre_dec, size_deg)
        content = await self.archive.download_bytes(url, self.max_bytes)
        png, meta = await asyncio.to_thread(render_png, content, stretch=stretch, low_pct=low_pct,
                                            high_pct=high_pct)
        meta.update(observation_id=observation_id, detector=product.get("detector"),
                    time_utc=product.get("t_min_utc"), collection=product.get("collection"),
                    centre={"ra": centre_ra, "dec": centre_dec, "frame": "ICRS"}, size_deg=size_deg,
                    source_fits_url=url, source="NASA/IPAC IRSA")
        self.cache.set(key, (png, meta))
        return png, meta
