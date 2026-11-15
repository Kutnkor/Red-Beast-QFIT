"""Retrieval of SPHEREx image and spectral products (references first, bytes only on request)."""
from __future__ import annotations

from typing import Any

from app.services.preview_service import PREVIEW_SIZE_DEG, preview_path
from app.astronomy.data_models import SPHEREX_BANDS, SpherexProduct
from app.astronomy.spherex_client import SpherexClient, cutout_url
from app.services.observation_service import (DEFAULT_RADIUS_DEG, IRSA_SOURCES, NO_DATA_REASONS,
                                              blocked_target, collections_for, dump, summarise)
from app.services.search_service import SearchService
from app.utils.errors import InvalidInputError, NotFoundError
from app.utils.validation import validate_ra_dec

SPECTRAL_IMAGE_NOTE = (
    "A SPHEREx Spectral Image is not a spectrum. Each of the six detectors images the sky through a "
    "linear variable filter, so the wavelength changes with pixel position. A full spectrum of one "
    "source is assembled from many exposures; a single file covers only one detector band.")
CUBE_NOTE = (
    "All-Sky Cube tiles (DR1) hold 102 nominal spectral channels per pixel with zodiacal light "
    "subtracted. IRSA documents that channels 51 and 52 contain no data. Tiles are large "
    "(about 300 MB) and use the HPX projection.")
CUBE_SOURCE = {"name": "SPHEREx DR1 Spectral All-Sky Cube (DOI 10.26131/IRSA679)",
               "url": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html"}
SPECTRO_TOOL = {"name": "IRSA SPHEREx Spectrophotometry Tool (science-grade spectra)",
                "url": "https://irsa.ipac.caltech.edu/applications/spherex/tool-spectrophotometry"}


def band_coverage(products: list[SpherexProduct]) -> list[dict[str, Any]]:
    out = []
    for detector in sorted({p.detector for p in products if p.detector}):
        group = [p for p in products if p.detector == detector]
        lows = [p.wavelength_min_um for p in group if p.wavelength_min_um is not None]
        highs = [p.wavelength_max_um for p in group if p.wavelength_max_um is not None]
        out.append({"detector": detector, "bandpass": group[0].bandpass, "files": len(group),
                    "wavelength_min_um": min(lows) if lows else None,
                    "wavelength_max_um": max(highs) if highs else None,
                    "resolving_power": group[0].resolving_power,
                    "nominal_band": SPHEREX_BANDS.get(detector)})
    return out


def spread_across_detectors(products: list[SpherexProduct], count: int) -> list[SpherexProduct]:
    """Pick up to `count` products, newest first, cycling through the detectors."""
    by_detector: dict[int, list[SpherexProduct]] = {}
    for product in sorted(products, key=lambda p: p.t_min_mjd or 0.0, reverse=True):
        by_detector.setdefault(product.detector or 0, []).append(product)
    chosen: list[SpherexProduct] = []
    while len(chosen) < count and any(by_detector.values()):
        for detector in sorted(by_detector):
            if by_detector[detector] and len(chosen) < count:
                chosen.append(by_detector[detector].pop(0))
    return chosen


class RetrievalService:
    def __init__(self, spherex: SpherexClient, search: SearchService):
        self.spherex = spherex
        self.search = search

    async def image_products(self, *, object_name: str | None = None, ra: float | None = None,
                             dec: float | None = None, cutout_size_deg: float = 0.1,
                             detector: int | None = None, release: str | None = None,
                             limit: int = 6, verify: bool = False) -> dict[str, Any]:
        if not 0 < cutout_size_deg <= 3.5:
            raise InvalidInputError("cutout_size_deg must be within (0, 3.5] degrees.")
        target = await self.search.resolve_target(object_name, ra, dec)
        if target.status != "ok":
            return {**blocked_target(target), "image_products": []}
        products, truncated = await self.spherex.search_products(
            target.ra, target.dec, DEFAULT_RADIUS_DEG, collections=collections_for(release))
        if detector is not None:
            products = [p for p in products if p.detector == detector]
        chosen = spread_across_detectors(products, limit) if detector is None else \
            sorted(products, key=lambda p: p.t_min_mjd or 0.0, reverse=True)[:limit]
        items = []
        for index, product in enumerate(chosen):
            item = dump(product)
            item["cutout_url"] = cutout_url(product.access_url, target.ra, target.dec, cutout_size_deg)
            item["cutout_size_deg"] = cutout_size_deg
            # 0.5 deg gives a ~290 px preview; 0.1 deg only ~60 px, which blurs when zoomed in. The
            # download time hardly changes: the cutout's size is dominated by its other extensions.
            item["preview_url"] = preview_path(product.observation_id, target.ra, target.dec, PREVIEW_SIZE_DEG)
            item["download_check"] = (await self.spherex.archive.probe_url(product.access_url)
                                      if verify and index < 5 else {"verified": None})
            items.append(item)
        available = bool(products)
        result = {
            "status": "ok" if available else "no_data", "spherex_available": available,
            "target": target.as_dict(), "object": target.object.model_dump() if target.object else None,
            "total_available": len(products), "returned": len(items),
            "truncated_by_archive_limit": truncated, "image_products": items,
            "format_note": ("access_url is the full multi-extension FITS file (about 60-70 MB; extensions "
                            "IMAGE, FLAGS, VARIANCE, ZODI, EPSF, WCS-WAVE). cutout_url asks IRSA's cutout "
                            "service for a FITS subset centred on the target. Surface brightness is in "
                            "MJy/sr and zodiacal light is not subtracted. " + SPECTRAL_IMAGE_NOTE),
            "message": (f"{len(items)} of {len(products)} available SPHEREx spectral image file(s), "
                        "newest first and spread across detectors." if available else
                        "The IRSA archive returned no SPHEREx spectral images for this position."),
            "sources": target.sources + IRSA_SOURCES,
        }
        if not available:
            result["possible_reasons"] = NO_DATA_REASONS
        return result

    async def spectral_products(self, *, object_name: str | None = None, ra: float | None = None,
                                dec: float | None = None, release: str | None = None,
                                extract_samples: bool = False, max_samples: int = 6) -> dict[str, Any]:
        target = await self.search.resolve_target(object_name, ra, dec)
        if target.status != "ok":
            return {**blocked_target(target), "spectral_products": []}
        products, truncated = await self.spherex.search_products(
            target.ra, target.dec, DEFAULT_RADIUS_DEG, collections=collections_for(release))
        cubes = await self.spherex.find_cube_tiles(target.ra, target.dec, DEFAULT_RADIUS_DEG)
        spectral = [{**dump(c), "spectral_channels": 102, "format_note": CUBE_NOTE} for c in cubes]
        available = bool(products or cubes)
        result: dict[str, Any] = {
            "status": "ok" if available else "no_data", "spherex_available": available,
            "target": target.as_dict(), "object": target.object.model_dump() if target.object else None,
            "spectral_products": spectral,
            "spectral_image_coverage": {"summary": summarise(products), "bands": band_coverage(products),
                                        "detectors_missing": [d for d in SPHEREX_BANDS
                                                              if d not in {p.detector for p in products}],
                                        "note": SPECTRAL_IMAGE_NOTE},
            "truncated_by_archive_limit": truncated,
            "samples": [], "samples_note": None,
            "sources": target.sources + IRSA_SOURCES + [CUBE_SOURCE, SPECTRO_TOOL],
        }
        if extract_samples and products:
            chosen = spread_across_detectors(products, max(1, min(max_samples, 12)))
            samples = await self.spherex.extract_spectral_samples(chosen, target.ra, target.dec)
            result["samples"] = sorted(samples, key=lambda s: (s.get("wavelength_um") is None,
                                                               s.get("wavelength_um") or 0))
            result["samples_note"] = (
                "Each sample is the calibrated surface brightness of the single detector pixel under "
                "the target in one exposure, with zodiacal light included. It is a raw reading, not "
                "aperture photometry and not a calibrated source spectrum.")
        bands = len(result["spectral_image_coverage"]["bands"])
        result["message"] = (
            f"Spectral data available: {len(cubes)} All-Sky Cube tile(s) with 102 channels, and "
            f"{len(products)} spectral image file(s) covering {bands} of 6 detector bands."
            if available else "The IRSA archive returned no SPHEREx spectral products for this position.")
        if not available:
            result["possible_reasons"] = NO_DATA_REASONS
        return result

    async def spectrum_for_observation(self, observation_id: str, ra: float | None = None,
                                       dec: float | None = None, extract: bool = False) -> dict[str, Any]:
        hint = None
        if ra is not None and dec is not None:
            hint = validate_ra_dec(ra, dec)
        products = await self.spherex.get_products_by_id(observation_id, position_hint=hint)
        if not products:
            raise NotFoundError(f"The IRSA archive has no SPHEREx product with id '{observation_id}'.")
        items = []
        for product in products:
            item = dump(product)
            if product.product_kind == "all_sky_cube":
                item.update(spectral_channels=102, format_note=CUBE_NOTE)
            else:
                item.update(spectral_channels=None, nominal_band=SPHEREX_BANDS.get(product.detector or 0),
                            format_note=SPECTRAL_IMAGE_NOTE)
            items.append(item)
        result: dict[str, Any] = {"status": "ok", "observation_id": observation_id,
                                  "spectral_products": items, "samples": [], "samples_note": None,
                                  "message": f"Spectral metadata for {len(items)} file(s).",
                                  "sources": IRSA_SOURCES + [SPECTRO_TOOL]}
        if extract:
            if hint is None:
                raise InvalidInputError("ra and dec are required to extract a spectral sample.")
            images = [p for p in products if p.product_kind == "spectral_image"][:6]
            result["samples"] = await self.spherex.extract_spectral_samples(images, *hint)
            result["samples_note"] = ("Raw single-pixel surface brightness per exposure (zodiacal light "
                                      "included); not aperture photometry.")
        return result
