from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Container, get_container
from app.astronomy.data_models import SPHEREX_BANDS, SPHEREX_COLLECTIONS
from app.config import APP_FULL_NAME, APP_NAME, APP_VERSION
from app.models.responses import ACTION_TYPES, QFitResponse
from app.utils.errors import QFitError

router = APIRouter(tags=["system"])
_STARTED = time.monotonic()


async def _probe(name: str, coro) -> dict:
    started = time.monotonic()
    try:
        await coro
        return {"service": name, "reachable": True, "latency_ms": round((time.monotonic() - started) * 1000)}
    except QFitError as exc:
        return {"service": name, "reachable": False, "detail": exc.message}


@router.get("/health", response_model=QFitResponse, summary="Backend health")
async def health(deep: bool = Query(False, description="Also probe the external data services"),
                 c: Container = Depends(get_container)) -> QFitResponse:
    data = {"status": "ok", "version": APP_VERSION, "uptime_s": round(time.monotonic() - _STARTED),
            "ai_configured": c.ai_configured, "ai_provider": c.ai_provider_name, "ai_model": c.settings.active_model,
            "ai_fallback_enabled": c.settings.ai_fallback_enabled, "chat_daily_budget": c.daily_budget.status(),
            "candidate_writes_protected": c.settings.team_token is not None,
            "instruction_version": c.settings.qfit_instruction_version, "rag_enabled": c.settings.rag_enabled,
            "knowledge_base": c.knowledge.status, "scientific_config": c.scientific.status(),
            "candidate_store": {"candidates": c.candidates.list(limit=1)["total"],
                                "log_chain_valid": c.candidates.chain_valid}}
    degraded = [name for name, ok in (("knowledge_base", c.knowledge.status.get("available")),
                                      ("candidate_log", c.candidates.chain_valid)) if not ok]
    if degraded:
        data["status"], data["degraded"] = "degraded", degraded
    if deep:
        data["upstream"] = await asyncio.gather(
            _probe("IRSA TAP", c.archive.request("GET", f"{c.archive.base_url}/TAP/availability")),
            _probe("JPL Horizons", c.horizons_http.request(
                "GET", c.settings.horizons_api_url, params={"format": "text", "COMMAND": "'499'",
                                                           "MAKE_EPHEM": "NO", "OBJ_DATA": "NO"})))
    return c.envelope({"intent": "health", "message": "Q-FIT backend is running.", "data": data})


@router.get("/capabilities", response_model=QFitResponse, summary="Supported features and data sources")
async def capabilities(c: Container = Depends(get_container)) -> QFitResponse:
    data = {
        "assistant": {"name": APP_NAME, "full_name": APP_FULL_NAME, "version": APP_VERSION,
                      "llm_provider": {"gemini": "Google Gemini", "openai": "OpenAI", "ollama": "Ollama (local model)"}.get(
                          c.ai_provider_name, c.ai_provider_name), "llm_model": c.settings.active_model,
                      "ai_configured": c.ai_configured},
        "features": ["natural_language_chat", "object_name_resolution", "catalog_cone_search",
                     "spherex_observation_search", "spherex_observation_metadata",
                     "spherex_image_products_and_cutouts", "spherex_spectral_products",
                     "observation_periods", "knowledge_base_search", "citizen_science_candidates",
                     "turkish_and_english_answers"],
        "not_supported_yet": ["movement_detection", "source_classification", "spectral_interpretation",
                              "moving_object_archive_search", "phase_threshold_evaluation"],
        "tools": c.registry.describe(),
        "action_types": list(ACTION_TYPES),
        "spherex": {"collections": SPHEREX_COLLECTIONS, "detector_bands": SPHEREX_BANDS,
                    "nominal_spectral_channels": 102, "wavelength_range_um": [0.75, 5.0]},
        "data_sources": [
            {"name": "NASA/IPAC IRSA - SPHEREx archive", "role": "SPHEREx observations, images, spectral cubes",
             "interfaces": ["SIA 2.0", "TAP (ADQL)", "IBE cutout service"], "url": c.settings.spherex_base_url},
            {"name": "SIMBAD (CDS)", "role": "Deep-sky object names, coordinates, types",
             "interfaces": ["astroquery.simbad (TAP)"], "url": "https://simbad.cds.unistra.fr/simbad/"},
            {"name": "CDS Sesame", "role": "Fallback name resolver", "interfaces": ["astropy name resolver"],
             "url": "https://cds.unistra.fr/cgi-bin/Sesame"},
            {"name": "JPL Horizons", "role": "Solar System body positions", "interfaces": ["Horizons REST API"],
             "url": "https://ssd.jpl.nasa.gov/horizons/"},
        ],
        "limits": {"max_search_radius_deg": c.settings.max_search_radius_deg,
                   "max_archive_records_per_query": c.settings.max_archive_records,
                   "max_request_body_bytes": c.settings.max_request_body_bytes,
                   "chat_rate_limit_per_minute": c.settings.chat_rate_limit_per_minute},
        "conventions": {"angles": "decimal degrees, ICRS", "time": "UTC ISO-8601 and MJD",
                        "wavelength": "micron", "surface_brightness": "MJy/sr"},
    }
    return c.envelope({"intent": "capabilities", "message": "Q-FIT capabilities and data sources.", "data": data})
