"""Domain models for astronomical data. Catalog data and SPHEREx mission data
are deliberately separate types so they can never be confused downstream."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CelestialObject(BaseModel):
    """A catalog entry. Says nothing about whether SPHEREx observed the object."""
    query_name: str
    name: str = Field(description="Canonical identifier in the source catalog")
    ra: float = Field(description="Right ascension, ICRS, decimal degrees")
    dec: float = Field(description="Declination, ICRS, decimal degrees")
    coordinate_frame: str = "ICRS"
    coordinate_unit: str = "deg"
    object_type: str | None = Field(None, description="Catalog object-type code")
    object_type_label: str | None = None
    matched_identifier: str | None = None
    catalog_source: Literal["SIMBAD", "CDS Sesame", "JPL Horizons"]
    source_url: str | None = None
    reference_bibcode: str | None = None
    is_solar_system: bool = False
    position_time_dependent: bool = False
    position_epoch_utc: str | None = Field(None, description="Epoch of the position (moving objects)")
    observer_location: str | None = None
    notes: list[str] = Field(default_factory=list)


class ResolveResult(BaseModel):
    status: Literal["resolved", "ambiguous", "not_found"]
    query_name: str
    object: CelestialObject | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    message: str
    sources: list[dict[str, str]] = Field(default_factory=list)


class SpherexProduct(BaseModel):
    """One file in the IRSA SPHEREx archive, as described by the archive itself."""
    observation_id: str = Field(description="Q-FIT id: collection:obs_id:product")
    obs_id: str
    collection: str
    release: str | None = None
    survey: str | None = None
    product_kind: Literal["spectral_image", "all_sky_cube", "other"]
    dataproduct_type: str | None = None
    calib_level: int | None = None
    detector: int | None = Field(None, description="SPHEREx detector / band number 1-6")
    bandpass: str | None = None
    center_ra: float | None = Field(None, description="Image center RA, ICRS deg (not the search target)")
    center_dec: float | None = None
    fov_deg: float | None = None
    pixel_scale_arcsec: float | None = None
    t_min_mjd: float | None = None
    t_max_mjd: float | None = None
    t_min_utc: str | None = None
    t_max_utc: str | None = None
    exposure_s: float | None = None
    wavelength_min_um: float | None = None
    wavelength_max_um: float | None = None
    resolving_power: float | None = None
    access_url: str | None = Field(None, description="Archive download URL, verbatim from IRSA")
    access_format: str | None = None
    est_size_kb: int | None = None
    cutout_url: str | None = Field(None, description="IRSA cutout-service URL centred on the search target")
    cloud_access: dict[str, Any] | None = None
    publisher_did: str | None = None
    release_date: str | None = None
    footprint: str | None = None
    metadata_source: Literal["IRSA SIA2", "IRSA TAP"] = "IRSA SIA2"
    extra: dict[str, Any] = Field(default_factory=dict)


SPHEREX_BANDS: dict[int, dict[str, Any]] = {
    1: {"wavelength_um": [0.75, 1.09], "resolving_power": 39},
    2: {"wavelength_um": [1.10, 1.62], "resolving_power": 41},
    3: {"wavelength_um": [1.63, 2.41], "resolving_power": 41},
    4: {"wavelength_um": [2.42, 3.82], "resolving_power": 35},
    5: {"wavelength_um": [3.83, 4.41], "resolving_power": 112},
    6: {"wavelength_um": [4.42, 5.00], "resolving_power": 128},
}

SPHEREX_COLLECTIONS: dict[str, dict[str, str]] = {
    "spherex_dr1": {"release": "DR1", "survey": "wide", "kind": "spectral_image",
                    "description": "DR1 Spectral Image MEFs, Wide Survey"},
    "spherex_dr1_deep": {"release": "DR1", "survey": "deep", "kind": "spectral_image",
                         "description": "DR1 Spectral Image MEFs, Deep Survey"},
    "spherex_qr3": {"release": "QR3", "survey": "wide", "kind": "spectral_image",
                    "description": "QR3 Spectral Image MEFs, Wide Survey"},
    "spherex_qr3_deep": {"release": "QR3", "survey": "deep", "kind": "spectral_image",
                         "description": "QR3 Spectral Image MEFs, Deep Survey"},
    "spherex_dr1_cube": {"release": "DR1", "survey": "all-sky", "kind": "all_sky_cube",
                         "description": "DR1 All-Sky Cube FITS tiles (102 nominal channels)"},
}
IMAGE_COLLECTIONS = [c for c, v in SPHEREX_COLLECTIONS.items() if v["kind"] == "spectral_image"]
CUBE_COLLECTION = "spherex_dr1_cube"
