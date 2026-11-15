from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from app.api.dependencies import Container, get_container
from app.models.requests import ConeSearchRequest, ObjectSearchRequest, ResolveRequest, TargetKind
from app.models.responses import QFitResponse
from app.services import response_builder as rb

router = APIRouter(tags=["objects"])


@router.post("/objects/search", response_model=QFitResponse, summary="Search catalog objects by name")
async def search_objects(body: ObjectSearchRequest, c: Container = Depends(get_container)) -> QFitResponse:
    result = await c.search.search_objects(body.query, body.max_results)
    return c.envelope(rb.from_resolve(result.model_dump(), "search_object"))


@router.post("/objects/by-coordinates", response_model=QFitResponse, summary="Catalog objects near a position")
async def objects_by_coordinates(body: ConeSearchRequest, c: Container = Depends(get_container)) -> QFitResponse:
    result = await c.search.objects_near(body.ra, body.dec, body.radius_deg, body.object_type, body.limit)
    return c.envelope(rb.from_cone(result))


@router.get("/objects/{object_id:path}", response_model=QFitResponse, summary="Object information")
async def get_object(object_id: str = Path(..., max_length=100, description="Object name or identifier, URL-encoded"),
                     target_kind: TargetKind = Query("auto"),
                     c: Container = Depends(get_container)) -> QFitResponse:
    result = await c.search.resolve(object_id, target_kind)
    return c.envelope(rb.from_resolve(result.model_dump(), "get_object"))


@router.post("/coordinates/resolve", response_model=QFitResponse, summary="Resolve a name to coordinates")
async def resolve_coordinates(body: ResolveRequest, c: Container = Depends(get_container)) -> QFitResponse:
    result = await c.search.resolve(body.name, body.target_kind, body.epoch_utc)
    return c.envelope(rb.from_resolve(result.model_dump()))
