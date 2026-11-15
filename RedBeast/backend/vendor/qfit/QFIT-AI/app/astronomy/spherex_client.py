"""SPHEREx-specific access on top of the IRSA archive client.

Everything returned here comes from an archive response. Nothing is
synthesised: URLs are copied from `access_url` (SIA2) or built from the
archive's own `uri` column (TAP), exactly as IRSA documents.
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import struct
from typing import Any, Sequence

from app.astronomy.archive_client import ArchiveClient
from app.astronomy.data_models import (CUBE_COLLECTION, IMAGE_COLLECTIONS, SPHEREX_COLLECTIONS,
                                       SpherexProduct)
from app.utils.cache import TTLCache
from app.utils.coordinates import meters_to_microns, mjd_to_iso
from app.utils.logging import get_logger
from app.utils.validation import parse_observation_id

log = get_logger("spherex")
_DID_RE = re.compile(r"^ivo://irsa\.ipac/(?P<collection>[^?]+)\?(?P<obs_id>[^/]+)/(?P<product>.+)$")
_DETECTOR_RE = re.compile(r"D([1-6])$")

_TAP_COLUMNS = (
    "p.obs_publisher_did, p.productid, p.calibrationlevel, p.dataproducttype, "
    "p.energy_bounds_lower, p.energy_bounds_upper, p.energy_resolvingpower, "
    "p.energy_bandpassname, p.time_bounds_lower, p.time_bounds_upper, p.time_exposure, "
    "p.position_samplesize, p.provenance_name, p.provenance_version, p.datarelease, p.pt, "
    "a.uri, a.contenttype, a.contentlength, a.contentchecksum"
)


def _f(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _i(value: str | None) -> int | None:
    number = _f(value)
    return int(number) if number is not None else None


def _detector(bandpass: str | None, product: str | None) -> int | None:
    for text in (bandpass, product):
        match = _DETECTOR_RE.search(text or "")
        if match:
            return int(match.group(1))
    return None


def make_observation_id(collection: str, obs_id: str, product: str) -> str:
    return f"{collection}:{obs_id}:{product}"


def cutout_url(access_url: str, ra: float, dec: float, size_deg: float) -> str:
    """IRSA cutout syntax: append ?center=RA,Dec&size=SIZE (degrees) to an on-premises URL."""
    return f"{access_url}?center={ra:.7f},{dec:.7f}&size={size_deg:g}"


def product_from_sia(row: dict[str, str | None]) -> SpherexProduct:
    did = row.get("obs_publisher_did") or ""
    match = _DID_RE.match(did)
    collection = row.get("obs_collection") or (match.group("collection") if match else "unknown")
    obs_id = row.get("obs_id") or (match.group("obs_id") if match else "unknown")
    product = match.group("product") if match else (row.get("energy_bandpassname") or "0")
    info = SPHEREX_COLLECTIONS.get(collection, {})
    cloud = None
    if row.get("cloud_access"):
        try:
            cloud = json.loads(row["cloud_access"])
        except ValueError:
            cloud = {"raw": row["cloud_access"]}
    t_min, t_max = _f(row.get("t_min")), _f(row.get("t_max"))
    return SpherexProduct(
        observation_id=make_observation_id(collection, obs_id, product.replace("/", "-")),
        obs_id=obs_id, collection=collection,
        release=info.get("release"), survey=info.get("survey"),
        product_kind=info.get("kind", "other"),  # type: ignore[arg-type]
        dataproduct_type=row.get("dataproduct_type"), calib_level=_i(row.get("calib_level")),
        detector=_detector(row.get("energy_bandpassname"), product),
        bandpass=row.get("energy_bandpassname"),
        center_ra=_f(row.get("s_ra")), center_dec=_f(row.get("s_dec")),
        fov_deg=_f(row.get("s_fov")), pixel_scale_arcsec=_f(row.get("s_pixel_scale")),
        t_min_mjd=t_min, t_max_mjd=t_max, t_min_utc=mjd_to_iso(t_min), t_max_utc=mjd_to_iso(t_max),
        exposure_s=_f(row.get("t_exptime")),
        wavelength_min_um=meters_to_microns(_f(row.get("em_min"))),
        wavelength_max_um=meters_to_microns(_f(row.get("em_max"))),
        resolving_power=_f(row.get("em_res_power")),
        access_url=row.get("access_url"), access_format=row.get("access_format"),
        est_size_kb=_i(row.get("access_estsize")), cloud_access=cloud, publisher_did=did or None,
        release_date=row.get("obs_release_date"), footprint=row.get("s_region"),
        metadata_source="IRSA SIA2",
        extra={k: row[k] for k in ("target_name", "proposal_title", "algorithm_name", "obs_intent")
               if row.get(k)},
    )


def _decode_point(ewkb_hex: str | None) -> tuple[float | None, float | None]:
    """Decode the PostGIS EWKB point IRSA stores in spherex.plane.pt -> (ra, dec)."""
    try:
        raw = bytes.fromhex(ewkb_hex or "")
        lon, lat = struct.unpack("<dd", raw[-16:])
        return lon % 360.0, lat
    except (ValueError, struct.error):
        return None, None


def product_from_tap(row: dict[str, str | None], base_url: str) -> SpherexProduct | None:
    match = _DID_RE.match(row.get("obs_publisher_did") or "")
    if not match or not row.get("uri"):
        return None
    collection, obs_id, product = match.group("collection", "obs_id", "product")
    info = SPHEREX_COLLECTIONS.get(collection, {})
    t_min, t_max = _f(row.get("time_bounds_lower")), _f(row.get("time_bounds_upper"))
    size = _i(row.get("contentlength"))
    ra, dec = _decode_point(row.get("pt"))
    return SpherexProduct(
        observation_id=make_observation_id(collection, obs_id, product), obs_id=obs_id,
        collection=collection, release=info.get("release"), survey=info.get("survey"),
        product_kind=info.get("kind", "other"),  # type: ignore[arg-type]
        dataproduct_type=row.get("dataproducttype"), calib_level=_i(row.get("calibrationlevel")),
        detector=_detector(row.get("energy_bandpassname"), product),
        bandpass=row.get("energy_bandpassname"), center_ra=ra, center_dec=dec,
        pixel_scale_arcsec=_f(row.get("position_samplesize")),
        t_min_mjd=t_min, t_max_mjd=t_max, t_min_utc=mjd_to_iso(t_min), t_max_utc=mjd_to_iso(t_max),
        exposure_s=_f(row.get("time_exposure")),
        wavelength_min_um=meters_to_microns(_f(row.get("energy_bounds_lower"))),
        wavelength_max_um=meters_to_microns(_f(row.get("energy_bounds_upper"))),
        resolving_power=_f(row.get("energy_resolvingpower")),
        access_url=f"{base_url}/{row['uri'].lstrip('/')}", access_format=row.get("contenttype"),
        est_size_kb=size // 1024 if size else None, publisher_did=row.get("obs_publisher_did"),
        release_date=row.get("datarelease"), metadata_source="IRSA TAP",
        extra={k: row[k] for k in ("provenance_name", "provenance_version", "contentchecksum")
               if row.get(k)},
    )


class SpherexClient:
    def __init__(self, archive: ArchiveClient, *, max_records: int = 5000,
                 max_cutout_bytes: int = 40_000_000, cache_ttl: float = 600):
        self.archive = archive
        self.max_records = max_records
        self.max_cutout_bytes = max_cutout_bytes
        self._seen = TTLCache(max(cache_ttl, 60), max_entries=20000)

    # -------------------------------------------------------------- searching
    async def search_products(self, ra: float, dec: float, radius_deg: float, *,
                              collections: Sequence[str] | None = None,
                              wavelength_um: tuple[float, float] | None = None,
                              time_mjd: tuple[float, float] | None = None,
                              ) -> tuple[list[SpherexProduct], bool]:
        """Archive products whose footprint intersects the search circle.

        Returns (products sorted by start time, truncated flag).
        """
        collections = list(collections or IMAGE_COLLECTIONS)
        band_m = (wavelength_um[0] * 1e-6, wavelength_um[1] * 1e-6) if wavelength_um else None
        rows = await self.archive.sia_search(collections=collections, ra=ra, dec=dec,
                                             radius_deg=radius_deg, maxrec=self.max_records,
                                             band_m=band_m, time_mjd=time_mjd)
        products: dict[str, SpherexProduct] = {}
        for row in rows:
            if not row.get("access_url"):
                continue  # a record without a download reference is not a retrievable product
            product = product_from_sia(row)
            products.setdefault(product.observation_id, product)
            self._seen.set(product.observation_id, product)
        ordered = sorted(products.values(), key=lambda p: (p.t_min_mjd or 0.0, p.detector or 0))
        return ordered, len(rows) >= self.max_records

    async def find_cube_tiles(self, ra: float, dec: float, radius_deg: float) -> list[SpherexProduct]:
        products, _ = await self.search_products(ra, dec, radius_deg, collections=[CUBE_COLLECTION])
        return products

    # -------------------------------------------------------------- id lookup
    async def get_products_by_id(self, observation_id: str, *,
                                 position_hint: tuple[float, float] | None = None) -> list[SpherexProduct]:
        collection, obs_id, product = parse_observation_id(observation_id)
        matches = lambda p: (p.obs_id == obs_id and (collection is None or p.collection == collection)  # noqa: E731
                             and (product is None or p.observation_id.endswith(f":{product}")))
        if collection and product:
            cached = self._seen.get(make_observation_id(collection, obs_id, product))
            if cached is not None:
                return [cached]
        if position_hint is not None:
            cols = [collection] if collection else IMAGE_COLLECTIONS + [CUBE_COLLECTION]
            found, _ = await self.search_products(*position_hint, 0.01, collections=cols)
            hits = [p for p in found if matches(p)]
            if hits:
                return hits
        if collection and product:
            where = f"p.obs_publisher_did = 'ivo://irsa.ipac/{collection}?{obs_id}/{product}'"
        else:
            where = f"p.obs_publisher_did LIKE 'ivo://irsa.ipac/{collection or 'spherex%'}?{obs_id}/%'"
        adql = (f"SELECT {_TAP_COLUMNS} FROM spherex.plane p "
                f"JOIN spherex.artifact a ON a.planeid = p.planeid WHERE {where}")
        rows = await self.archive.tap_query(adql)
        out = []
        for row in rows:
            item = product_from_tap(row, self.archive.base_url)
            if item is not None and matches(item):
                out.append(item)
                self._seen.set(item.observation_id, item)
        return sorted(out, key=lambda p: (p.collection, p.detector or 0))

    # ----------------------------------------------------- spectral sampling
    async def extract_spectral_samples(self, products: Sequence[SpherexProduct], ra: float,
                                       dec: float, *, cutout_size_deg: float = 0.01) -> list[dict[str, Any]]:
        """For each spectral image, download a tiny cutout and read the calibrated
        surface brightness and wavelength of the pixel under (ra, dec).

        This is a raw per-pixel reading, not aperture photometry.
        """
        async def one(product: SpherexProduct) -> dict[str, Any]:
            base = {"observation_id": product.observation_id, "detector": product.detector,
                    "t_min_utc": product.t_min_utc}
            if product.product_kind != "spectral_image" or not product.access_url:
                return {**base, "ok": False, "error": "not a spectral image product"}
            url = cutout_url(product.access_url, ra, dec, cutout_size_deg)
            try:
                content = await self.archive.download_bytes(url, self.max_cutout_bytes)
                sample = await asyncio.to_thread(read_pixel_sample, content, ra, dec)
            except Exception as exc:  # one bad file must not sink the batch
                log.warning("spectral sample failed", extra={"observation_id": product.observation_id,
                                                             "error": type(exc).__name__})
                return {**base, "ok": False, "cutout_url": url,
                        "error": getattr(exc, "message", None) or f"could not read cutout ({type(exc).__name__})"}
            return {**base, "ok": True, "cutout_url": url, **sample}

        results = []
        # At most 2 concurrent downloads: IRSA's cutout service answered 503 to 5 of 6 requests
        # sent 3 at a time (2026-11-14), and succeeded when they were spaced out.
        for start in range(0, len(products), 2):
            results += await asyncio.gather(*(one(p) for p in products[start:start + 2]))
        return results


def read_pixel_sample(fits_bytes: bytes, ra: float, dec: float) -> dict[str, Any]:
    """Read one pixel from a SPHEREx Spectral Image cutout (IMAGE/VARIANCE/FLAGS/ZODI
    extensions plus the spectral 'W' WCS), following IRSA's SPHEREx tutorial."""
    import numpy as np
    from astropy.coordinates import SkyCoord
    from astropy.io import fits
    from astropy.wcs import WCS

    from astropy import log as astropy_log
    # SPHEREx IMAGE headers carry SIP distortion coefficients with a plain RA---TAN CTYPE.
    # astropy applies the SIP terms (the intended distortion model) and logs a long INFO note
    # on every file; keep that note out of the server log.
    astropy_log.setLevel("WARNING")
    with fits.open(io.BytesIO(fits_bytes), memmap=False) as hdul:
        image = hdul["IMAGE"]
        wcs = WCS(image.header)
        x, y = wcs.world_to_pixel(SkyCoord(ra, dec, unit="deg", frame="icrs"))
        xi, yi = int(round(float(x))), int(round(float(y)))
        ny, nx = image.data.shape
        if not (0 <= xi < nx and 0 <= yi < ny):
            raise ValueError("target position falls outside the cutout")

        def pixel(name: str) -> float | None:
            if name not in hdul:
                return None
            value = hdul[name].data[yi, xi]
            return float(value) if np.isfinite(value) else None

        out: dict[str, Any] = {
            "pixel_xy": [xi, yi],
            "surface_brightness": pixel("IMAGE"),
            # Real files write "MJy / sr"; the API contract uses the compact form everywhere.
            "surface_brightness_unit": "".join(str(image.header.get("BUNIT", "MJy/sr")).split()),
            "variance": pixel("VARIANCE"),
            "variance_unit": "(MJy/sr)^2",
            "zodi_model": pixel("ZODI"),
            "flags": int(hdul["FLAGS"].data[yi, xi]) if "FLAGS" in hdul else None,
            "zodiacal_light_subtracted": False,
            "wavelength_um": None, "bandwidth_um": None,
        }
        try:
            spectral = WCS(header=image.header, fobj=hdul, key="W")
            spectral.sip = None
            wavelength, bandwidth = spectral.pixel_to_world(float(x), float(y))
            out["wavelength_um"] = round(float(wavelength.to_value("um")), 5)
            out["bandwidth_um"] = round(float(bandwidth.to_value("um")), 5)
        except Exception as exc:
            out["wavelength_note"] = f"spectral WCS could not be evaluated ({type(exc).__name__})"
        return out
