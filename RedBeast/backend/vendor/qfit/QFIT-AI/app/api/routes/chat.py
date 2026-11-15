from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import Container, client_ip, get_container
from app.models.requests import ChatRequest
from app.models.responses import QFitResponse
from app.services.fallback import knowledge_fallback
from app.utils.errors import AIUnavailableError, RateLimitedError, UpstreamError
from app.utils.logging import get_logger

router = APIRouter(tags=["assistant"])
log = get_logger("chat")


@router.post("/chat", response_model=QFitResponse, summary="Natural-language assistant")
async def chat(body: ChatRequest, request: Request, c: Container = Depends(get_container)) -> QFitResponse:
    """Understands the request with the configured model (OpenAI, Gemini or a local Ollama model) and
    function calling, runs the data tools and returns the explanation (`message`, AI-generated)
    together with the retrieved data and UI actions. When the model cannot be used (not
    configured, out of quota, unreachable), the answer falls back to a cited knowledge-base
    passage: `data.fallback.active` is then true and `message_source` is "system"."""
    c.rate_limiter.check(client_ip(request))   # per-client abuse limit: never falls back
    context = body.context.model_dump() if body.context else None
    if c.ai_configured and not c.daily_budget.take():
        budget = RateLimitedError("The daily AI budget of this site is used up; answers come from the knowledge "
                                  "base until midnight UTC.", details={"quota": "site_daily_budget"})
        if not c.settings.ai_fallback_enabled:
            raise budget
        return c.envelope(knowledge_fallback(c.knowledge, body.message, context, budget))
    try:
        agent = c.agent
        try:
            result = await asyncio.wait_for(agent.run(body.message, [t.model_dump() for t in body.history], context),
                                            timeout=c.settings.chat_timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise UpstreamError(f"The answer took longer than {c.settings.chat_timeout_seconds:g} s "
                                "(a data archive or the AI service is slow).") from exc
    except (AIUnavailableError, RateLimitedError, UpstreamError) as exc:
        if not c.settings.ai_fallback_enabled:
            raise
        log.warning("chat fallback", extra={"reason": exc.code})
        return c.envelope(knowledge_fallback(c.knowledge, body.message, context, exc))
    parts = {**result.parts, "intent": result.intent, "message": result.text}
    return c.envelope(parts, message_source="ai_generated", ai_model=result.model,
                      tools_called=[r.name for r in result.tool_runs])
