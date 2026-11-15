from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import Container, get_container
from app.models.requests import KnowledgeSearchRequest
from app.models.responses import QFitResponse
from app.services import response_builder as rb

router = APIRouter(tags=["knowledge"])


@router.post("/knowledge/search", response_model=QFitResponse, summary="Search the verified knowledge base")
async def search_knowledge(body: KnowledgeSearchRequest, c: Container = Depends(get_container)) -> QFitResponse:
    """BM25 search over the curated TR/EN knowledge passages. Every passage carries its sources."""
    result = c.knowledge.search(body.query, language=body.language, top_k=body.top_k, topic=body.topic)
    return c.envelope({**rb.from_knowledge(result), "language": result["language"]})


@router.get("/knowledge/sources", response_model=QFitResponse, summary="The scientific source registry")
async def knowledge_sources(c: Container = Depends(get_container)) -> QFitResponse:
    sources = c.knowledge.sources()
    status = c.knowledge.status
    return c.envelope({"intent": "knowledge_sources",
                       "message": f"{len(sources)} registered scientific source(s).",
                       "data": {"registry_version": status.get("registry_version"),
                                "knowledge_base": status, "registry": sources}})
