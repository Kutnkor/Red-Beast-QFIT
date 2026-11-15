"""Application container, FastAPI dependencies and envelope helpers."""
from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import Request

from app.ai.agent import QFitAgent
from app.ai.llm_provider import LLMProvider
from app.ai.tool_registry import ToolRegistry, build_registry
from app.astronomy.archive_client import ArchiveClient
from app.astronomy.horizons_client import HorizonsClient
from app.astronomy.object_resolver import ObjectResolver
from app.astronomy.spherex_client import SpherexClient
from app.citizen.store import CandidateStore
from app.config import Settings
from app.knowledge.service import APP_ROOT, KnowledgeBase
from app.models.responses import ErrorInfo, Meta, QFitResponse, empty_data
from app.scientific.config_loader import ScientificConfig
from app.services.observation_service import ObservationService
from app.services.preview_service import PreviewService
from app.services.retrieval_service import RetrievalService
from app.services.search_service import SearchService
from app.utils.errors import AIUnavailableError, RateLimitedError, UnauthorizedError
from app.utils.logging import request_id_var


class RateLimiter:
    """Sliding-window limiter per client, protecting the paid LLM endpoint."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client: str) -> None:
        if self.per_minute <= 0:
            return
        now, hits = time.monotonic(), self._hits[client]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            raise RateLimitedError("Too many chat requests. Please wait a moment and try again.")
        hits.append(now)


class DailyBudget:
    """Caps model calls per UTC day for the whole site, so a public page cannot drain the API
    credit. When the cap is reached /chat answers from the knowledge base until midnight UTC."""

    def __init__(self, limit: int):
        self.limit = limit
        self.day = ""
        self.used = 0

    def _roll(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.day:
            self.day, self.used = today, 0

    def take(self) -> bool:
        """Reserve one model call. False when today's budget is used up."""
        if self.limit <= 0:
            return True
        self._roll()
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    def status(self) -> dict[str, Any]:
        self._roll()
        return {"limit_per_day": self.limit or None, "used_today": self.used, "day_utc": self.day,
                "remaining": None if self.limit <= 0 else max(self.limit - self.used, 0)}


def client_ip(request: Request) -> str:
    """With TRUST_PROXY_HEADERS uvicorn already replaced request.client with the X-Forwarded-For
    address; without it the header is ignored, so a caller cannot fake its IP."""
    return request.client.host if request.client else "unknown"


def require_team_token(request: Request) -> None:
    """Candidate writes need the team token (header X-QFit-Token) when QFIT_TEAM_TOKEN is set."""
    expected = request.app.state.container.settings.team_token
    if expected is None:
        return
    given = request.headers.get("X-QFit-Token", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise UnauthorizedError("This action needs the team token (header X-QFit-Token).")


class Container:
    """Builds and owns every long-lived component. Tests inject transports/providers."""

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None,
                 provider: LLMProvider | None = None, resolver: ObjectResolver | None = None,
                 knowledge: KnowledgeBase | None = None, scientific: ScientificConfig | None = None,
                 candidates: CandidateStore | None = None):
        self.settings = settings
        common = dict(timeout=settings.http_timeout_seconds, max_retries=settings.http_max_retries,
                      cache_ttl=settings.cache_ttl_seconds, transport=transport)
        self.archive = ArchiveClient(settings.spherex_base_url, **common)
        self.horizons_http = ArchiveClient(settings.horizons_api_url, **common)
        self.horizons = HorizonsClient(self.horizons_http, settings.horizons_api_url)
        self.resolver = resolver or ObjectResolver(self.horizons, timeout=settings.http_timeout_seconds,
                                                   cache_ttl=settings.cache_ttl_seconds)
        self.spherex = SpherexClient(self.archive, max_records=settings.max_archive_records,
                                     max_cutout_bytes=settings.max_cutout_download_bytes,
                                     cache_ttl=settings.cache_ttl_seconds)
        self.search = SearchService(self.resolver, settings.max_search_radius_deg)
        self.observations = ObservationService(self.spherex, self.search, settings.max_search_radius_deg)
        self.retrieval = RetrievalService(self.spherex, self.search)
        self.previews = PreviewService(self.observations, self.archive, settings.max_cutout_download_bytes)
        if knowledge is None:
            knowledge = KnowledgeBase()
            knowledge.load()       # never raises: a broken knowledge base is reported in /health
        self.knowledge = knowledge
        self.scientific = scientific or ScientificConfig()
        self.scientific.load()
        self.candidates = candidates or CandidateStore(self.data_dir / "citizen" / "events.jsonl")
        self.registry: ToolRegistry = build_registry(self.search, self.observations, self.retrieval,
                                                     knowledge=self.knowledge, candidates=self.candidates)
        self.rate_limiter = RateLimiter(settings.chat_rate_limit_per_minute)
        self.daily_budget = DailyBudget(settings.chat_daily_limit)
        self._provider = provider
        self._agent: QFitAgent | None = None

    @property
    def data_dir(self) -> Path:
        path = Path(self.settings.qfit_data_dir).expanduser()
        return path if path.is_absolute() else APP_ROOT / path

    def versions(self) -> dict[str, Any]:
        """What an answer was produced with, so it can be reproduced and audited."""
        kb = self.knowledge.status
        return {"instructions": self.settings.qfit_instruction_version,
                "knowledge_index": kb.get("index_version"), "source_registry": kb.get("registry_version"),
                "scientific_config": self.scientific.version}

    def envelope(self, parts: dict[str, Any], **kwargs: Any) -> QFitResponse:
        return envelope(parts, versions=self.versions(), **kwargs)

    @property
    def ai_configured(self) -> bool:
        if self._provider is not None:
            return True
        if self.settings.llm_provider == "ollama":
            return bool(self.settings.ollama_model)
        if self.settings.llm_provider == "openai":
            return self.settings.openai_key is not None and bool(self.settings.openai_model)
        return self.settings.gemini_key is not None

    @property
    def ai_provider_name(self) -> str:
        if self._provider is not None:
            return getattr(self._provider, "name", "custom")
        return self.settings.llm_provider

    def _build_provider(self) -> LLMProvider:
        s = self.settings
        if s.llm_provider == "ollama":
            if not s.ollama_model:
                raise AIUnavailableError("The AI assistant is not configured: LLM_PROVIDER is 'ollama' but "
                                         "OLLAMA_MODEL is empty. The structured data endpoints work without it.")
            from app.ai.ollama_client import OllamaProvider
            return OllamaProvider(s.ollama_base_url, s.ollama_model, timeout_seconds=max(s.ai_timeout_seconds, 120))
        if s.llm_provider == "openai":
            if s.openai_key is None or not s.openai_model:
                raise AIUnavailableError("The AI assistant is not configured: LLM_PROVIDER is 'openai' but "
                                         "OPENAI_API_KEY or OPENAI_MODEL is empty. The structured data endpoints "
                                         "work without it.")
            from app.ai.openai_client import OpenAIProvider
            return OpenAIProvider(s.openai_key, s.openai_model, base_url=s.openai_base_url,
                                  timeout_seconds=s.ai_timeout_seconds, reasoning_effort=s.openai_reasoning_effort)
        if s.gemini_key is None:
            raise AIUnavailableError(
                "The AI assistant is not configured: set GEMINI_API_KEY on the server. "
                "The structured data endpoints work without it.")
        from app.ai.gemini_client import GeminiProvider
        return GeminiProvider(s.gemini_key, s.gemini_model, timeout_seconds=s.ai_timeout_seconds)

    @property
    def agent(self) -> QFitAgent:
        if self._agent is None:
            if self._provider is None:
                self._provider = self._build_provider()
            self._agent = QFitAgent(self._provider, self.registry, self.settings.ai_max_tool_steps,
                                    knowledge=self.knowledge,
                                    instruction_version=self.settings.qfit_instruction_version,
                                    rag_enabled=self.settings.rag_enabled, rag_top_k=self.settings.rag_top_k)
        return self._agent

    async def aclose(self) -> None:
        await self.archive.aclose()
        await self.horizons_http.aclose()
        closer = getattr(self._provider, "aclose", None)
        if closer is not None:
            await closer()


def get_container(request: Request) -> Container:
    return request.app.state.container


def envelope(parts: dict[str, Any], *, success: bool = True, message_source: str = "system",
             tools_called: list[str] | None = None, ai_model: str | None = None,
             error: ErrorInfo | None = None, versions: dict[str, Any] | None = None) -> QFitResponse:
    data = {**empty_data(), **parts.get("data", {})}
    return QFitResponse(
        success=success, intent=parts.get("intent", "unknown"), message=parts.get("message", ""),
        message_source=message_source, object=parts.get("object"), data=data,  # type: ignore[arg-type]
        actions=parts.get("actions", []), sources=parts.get("sources", []), language=parts.get("language"),
        evidence=parts.get("evidence", []), uncertainty=parts.get("uncertainty", []),
        media=parts.get("media", []), error=error,
        meta=Meta(request_id=request_id_var.get(), tools_called=tools_called or [], ai_model=ai_model,
                  versions=versions or {}))


def error_envelope(code: str, message: str, *, retryable: bool = False,
                   details: dict[str, Any] | None = None) -> QFitResponse:
    info = ErrorInfo(code=code, message=message, retryable=retryable, details=details or {})
    return envelope({"intent": "error", "message": message,
                     "actions": [{"type": "show_error", "payload": {"code": code, "message": message}}]},
                    success=False, error=info)
