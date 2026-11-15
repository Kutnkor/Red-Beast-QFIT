from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response

from app.api.dependencies import Container, get_container
from app.models.requests import ImageSearchRequest, ObservationSearchRequest, PeriodsRequest, Release
from app.models.responses import QFitResponse
from app.services import response_builder as rb

router = APIRouter(tags=["observations"])


@router.get("/observations", response_model=QFitResponse, summary="SPHEREx observations for a target")
async def list_observations(
        object: str | None = Query(None, max_length=100, description="Object name (alternative to ra/dec)"),
        ra: float | None = Query(None, ge=0, le=360), dec: float | None = Query(None, ge=-90, le=90),
        radius_deg: float = Query(0.003, gt=0, le=2), detector: int | None = Query(None, ge=1, le=6),
        release: Release = Query("all"), start_utc: str | None = Query(None, max_length=40),
        end_utc: str | None = Query(None, max_length=40), limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0), c: Container = Depends(get_container)) -> QFitResponse:
    body = ObservationSearchRequest(object_name=object, ra=ra, dec=dec, radius_deg=radius_deg,
                                    detector=detector, release=release, start_utc=start_utc,
                                    end_utc=end_utc, limit=limit, offset=offset)
    return c.envelope(rb.from_observations(await c.observations.search_observations(**body.model_dump())))


@router.post("/observations/search", response_model=QFitResponse, summary="Structured SPHEREx archive search")
async def search_observations(body: ObservationSearchRequest, c: Container = Depends(get_container)) -> QFitResponse:
    return c.envelope(rb.from_observations(await c.observations.search_observations(**body.model_dump())))


@router.post("/observations/periods", response_model=QFitResponse, summary="Observation periods for a target")
async def observation_periods(body: PeriodsRequest, c: Container = Depends(get_container)) -> QFitResponse:
    return c.envelope(rb.from_periods(await c.observations.observation_periods(**body.model_dump())))


@router.post("/images/search", response_model=QFitResponse, summary="SPHEREx image products and cutout URLs")
async def search_images(body: ImageSearchRequest, c: Container = Depends(get_container)) -> QFitResponse:
    return c.envelope(rb.from_images(await c.retrieval.image_products(**body.model_dump())))


def _preview_args(observation_id: str = Query(..., max_length=120, description="Spectral image id, e.g. spherex_qr3:2026W21_1A_0491_2:D4"),
                  ra: float | None = Query(None, ge=0, le=360, description="Cutout centre RA (default: image centre)"),
                  dec: float | None = Query(None, ge=-90, le=90),
                  size_deg: float = Query(0.5, gt=0, le=1.0, description="Cutout side in degrees"),
                  stretch: Literal["asinh", "log", "linear"] = Query("asinh"),
                  low_pct: float = Query(1.0, ge=0, lt=50), high_pct: float = Query(99.5, gt=50, le=100)) -> dict:
    return dict(observation_id=observation_id, ra=ra, dec=dec, size_deg=size_deg, stretch=stretch,
                low_pct=low_pct, high_pct=high_pct)


@router.get("/images/preview", response_class=Response, summary="PNG preview of a SPHEREx spectral image",
            responses={200: {"content": {"image/png": {}}, "description": "Grey + alpha PNG"}})
async def image_preview(args: dict = Depends(_preview_args), c: Container = Depends(get_container)) -> Response:
    """A PNG a browser or Three.js `TextureLoader` can load. Downloads an IRSA cutout (can take
    20-45 s the first time, then cached for an hour). A display image, not a measurement: see
    `/images/preview/info` for the stretch range and the sky position of the corners."""
    args = dict(args)
    png, meta = await c.previews.preview(args.pop("observation_id"), **args)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600",
                             "X-QFit-Note": "display image, not a measurement"})


@router.get("/images/preview/info", response_model=QFitResponse, summary="Metadata of a PNG preview")
async def image_preview_info(args: dict = Depends(_preview_args), c: Container = Depends(get_container)) -> QFitResponse:
    """Same cutout as /images/preview: size, stretch range (MJy/sr) and the ICRS position of the PNG's
    four corners, so the texture can be placed on the sky (SPHEREx images are not north-up)."""
    args = dict(args)
    observation_id = args.pop("observation_id")
    _, meta = await c.previews.preview(observation_id, **args)
    from app.services.preview_service import preview_path
    url = preview_path(observation_id, args["ra"], args["dec"], args["size_deg"], args["stretch"])
    return c.envelope({"intent": "image_preview", "message": f"PNG preview of {observation_id}.",
                       "data": {"preview": {**meta, "png_url": url}},
                       "media": [{"media_type": "png_preview", "url": url, "full_file_url": meta["source_fits_url"],
                                  "observation_id": observation_id, "detector": meta.get("detector"),
                                  "time_utc": meta.get("time_utc"), "collection": meta.get("collection"),
                                  "source": "NASA/IPAC IRSA", "verified": True}],
                       "uncertainty": [meta["note"]],
                       "sources": [{"name": "NASA/IPAC IRSA - SPHEREx archive (cutout service)",
                                    "url": "https://irsa.ipac.caltech.edu/Missions/spherex.html"}]})


@router.get("/observations/{observation_id}", response_model=QFitResponse, summary="Observation metadata")
async def get_observation(
        observation_id: str = Path(..., max_length=120, description="e.g. spherex_qr3:2026W21_1A_0491_2:D4"),
        ra: float | None = Query(None, ge=0, le=360, description="Optional position hint (faster lookup)"),
        dec: float | None = Query(None, ge=-90, le=90), c: Container = Depends(get_container)) -> QFitResponse:
    return c.envelope(rb.from_observation_detail(await c.observations.get_observation(observation_id, ra, dec)))
