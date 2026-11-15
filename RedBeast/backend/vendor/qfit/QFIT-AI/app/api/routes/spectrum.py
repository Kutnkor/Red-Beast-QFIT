from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from app.api.dependencies import Container, get_container
from app.models.requests import SpectrumSearchRequest
from app.models.responses import QFitResponse
from app.services import response_builder as rb

router = APIRouter(tags=["spectrum"])


@router.post("/spectrum/search", response_model=QFitResponse, summary="Spectral products for a target")
async def search_spectrum(body: SpectrumSearchRequest, c: Container = Depends(get_container)) -> QFitResponse:
    return c.envelope(rb.from_spectral(await c.retrieval.spectral_products(**body.model_dump())))


@router.get("/spectrum/{observation_id}", response_model=QFitResponse, summary="Spectral information of an observation")
async def get_spectrum(
        observation_id: str = Path(..., max_length=120),
        ra: float | None = Query(None, ge=0, le=360, description="Target RA: required with extract=true"),
        dec: float | None = Query(None, ge=-90, le=90),
        extract: bool = Query(False, description="Read the pixel value and wavelength at ra/dec from a cutout"),
        c: Container = Depends(get_container)) -> QFitResponse:
    result = await c.retrieval.spectrum_for_observation(observation_id, ra, dec, extract)
    return c.envelope(rb.from_spectral(result))
