"""Disabled-by-default assistant contract, local mock and lazy QFIT adapter."""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


_PRIVATE_KEYS = frozenset({"note", "notes", "edit_key", "edit_token", "edit_token_hash", "api_key", "password", "authorization"})


def _check_context(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in _PRIVATE_KEYS:
                raise ValueError("private fields are not allowed in assistant context")
            _check_context(child)
    elif isinstance(value, list):
        for child in value:
            _check_context(child)


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_use_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    ok: bool
    result: dict[str, Any] = Field(default_factory=dict)

    @field_validator("result")
    @classmethod
    def small_result(cls, value):
        if len(_json_bytes(value)) > 4096:
            raise ValueError("tool result exceeds 4096 UTF-8 bytes")
        _check_context(value)
        return value


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(default="", max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=10)
    tool_results: list[ToolResult] = Field(default_factory=list, max_length=10)

    @field_validator("context")
    @classmethod
    def small_public_context(cls, value):
        if len(_json_bytes(value)) > 4096:
            raise ValueError("assistant context exceeds 4096 UTF-8 bytes")
        _check_context(value)
        return value

    @model_validator(mode="after")
    def meaningful_request(self):
        if not self.message.strip() and not self.tool_results:
            raise ValueError("message or tool_results is required")
        return self


@dataclass(frozen=True)
class Event:
    name: Literal["text", "command", "sources", "done", "error"]
    data: Any

    def encode(self) -> str:
        return f"event: {self.name}\ndata: {_json_bytes(self.data).decode('utf-8')}\n\n"


class AssistantProvider(Protocol):
    def stream(self, system: str, messages: ChatInput, tools: tuple[str, ...]) -> Iterator[Event]: ...


COMMAND_NAMES = (
    "select_target", "set_mode", "set_year", "set_frame", "set_view_mode", "set_stage_view",
    "toggle_layer", "open_drawer_tab", "open_sources", "start_search", "save_view",
    "open_target", "set_stellar_mode", "set_sky_scale", "explain_value",
)


class MockProvider:
    """Fixed demonstrations, never an astronomical interpretation of the message."""

    def stream(self, system: str, messages: ChatInput, tools: tuple[str, ...]) -> Iterator[Event]:
        tr = messages.context.get("ui_language") == "tr"
        if messages.tool_results:
            failed = any(not result.ok for result in messages.tool_results)
            if failed:
                yield Event("error", {"code": "command_not_completed", "message": "Komut tamamlanmadı." if tr else "The command was not completed."})
            else:
                yield Event("text", {"delta": "Komut sonucu alındı. Bu yerel bir deneme yanıtıdır." if tr else "The command result was received. This is a local mock response."})
            yield Event("done", {"stop_reason": "end_turn"})
            return

        yield Event("text", {"delta": (
            "Bu yerel bir deneme yanıtıdır; bir model çağrılmadı. 3B yol hesaplanır, yıldız yüzeyi temsili olarak çizilir. "
            "SPHEREx görüntüleri ayrı gözlemlerdir; hesaplanan yol bilimsel doğrulama değildir."
            if tr else
            "This is a local mock response; no model was called. The 3D path is computed and the stellar surface is representative. "
            "SPHEREx frames are separate observations; a computed path is not scientific confirmation."
        )})
        # Fixed strings let tests exercise both an ordinary command and a gated action.
        # No natural-language intent inference is claimed.
        if messages.message.strip().lower() == "mock:save":
            name, args, confirmation = "save_view", {}, True
        elif messages.message.strip().lower() == "mock:search":
            name, args, confirmation = "start_search", {"ra": "269.452075", "dec": "4.693391", "ra_unit": "deg", "fov_arcmin": 6}, True
        else:
            name, args, confirmation = "set_year", {"year": 2100}, False
        yield Event("command", {"tool_use_id": "mock_command_1", "name": name, "args": args, "requires_confirmation": confirmation})
        yield Event("sources", ["motion#model", "epistemic#labels", "method#6"])
        yield Event("done", {"stop_reason": "tool_use"})


class DailyCounter:
    """Process-local UTC-day count. One server worker is required by deployment."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self.day: int | None = None
        self.count = 0
        self.lock = threading.Lock()

    def allow(self, limit: int) -> bool:
        with self.lock:
            day = int(self.clock() // 86400)
            if day != self.day:
                self.day, self.count = day, 0
            if self.count >= limit:
                return False
            self.count += 1
            return True


def _provider_name() -> str | None:
    name = os.environ.get("BLINKSPACE_ASSISTANT_PROVIDER", "").strip().lower()
    if name == "mock":
        return name
    if name == "qfit":
        from .assistant_qfit import availability
        return name if availability()["enabled"] else None
    return None


def _daily_limit() -> int:
    try:
        return max(0, int(os.environ.get("BLINKSPACE_ASSISTANT_DAILY_LIMIT", "100")))
    except ValueError:
        return 0  # Fail closed on an invalid limit, without logging user input.


def build_assistant_router(rate_limiter_factory) -> APIRouter:
    """Use the API's existing RateLimiter implementation without circular imports."""
    router = APIRouter(prefix="/api/assistant", tags=["assistant"])
    limiter = rate_limiter_factory(6, 60.0)
    daily = DailyCounter()

    @router.get("/status")
    def status():
        if os.environ.get("BLINKSPACE_ASSISTANT_PROVIDER", "").strip().lower() == "qfit":
            from .assistant_qfit import availability
            return availability()
        provider = _provider_name()
        return {"enabled": provider is not None, "provider": provider}

    @router.get("/commands")
    def commands():
        from .assistant_commands import schemas
        return schemas()

    @router.get("/sources/{source_id:path}")
    def source(source_id: str):
        from .assistant_qfit import local_sources
        item = local_sources().get(source_id)
        if item is None:
            raise HTTPException(404, detail="Unknown source")
        return item

    @router.post("/knowledge")
    def knowledge(body: ChatInput):
        """The quickest answer without a model: navigation, catalogue facts, a sourced passage or the target card."""
        from .assistant_intent import answer
        return answer(body)

    @router.get("/targets")
    def targets():
        """The stars a command may name, so a client can resolve names without loading the whole catalogue."""
        from .assistant_intent import ALIASES, directory
        return {"targets": [{"id": item["star"]["id"], "name": item["star"]["name"], "ready": item["star"]["id"] in ALIASES,
                             "aliases": ALIASES.get(item["star"]["id"], [])} for item in directory()]}

    @router.post("/chat")
    async def chat(body: ChatInput, request: Request):
        provider = _provider_name()
        if provider is None:
            raise HTTPException(503, detail={"code": "assistant_disabled", "message": "Assistant is disabled."})
        ip = request.client.host if request.client else "unknown"
        if not limiter.allow(ip):
            raise HTTPException(429, detail={"code": "assistant_rate_limit", "message": "Try again in a minute."}, headers={"Retry-After": "60"})
        if provider == "mock" and not daily.allow(_daily_limit()):
            raise HTTPException(429, detail={"code": "assistant_daily_limit", "message": "The daily request limit has been reached."})

        def stream():
            try:
                for event in MockProvider().stream("local mock", body, COMMAND_NAMES):
                    yield event.encode()
            except Exception:
                # Deliberately avoid exception messages and request content in logs/events.
                yield Event("error", {"code": "assistant_stream_error", "message": "The assistant stream ended unexpectedly."}).encode()
                yield Event("done", {"stop_reason": "error"}).encode()

        async def qfit_stream():
            from .assistant_intent import instant
            from .assistant_qfit import local_answer, run_qfit
            # Navigation and catalogue look-ups need no model round: answer at once and spend no budget.
            quick = None if body.tool_results else instant(body)
            if quick is not None:
                for proposal in quick["commands"]:
                    yield Event("command", proposal).encode()
                yield Event("text", {"delta": quick["message"]}).encode()
                yield Event("sources", [s.get("id") or s.get("url") for s in quick["sources"]]).encode()
                yield Event("done", {"stop_reason": "tool_use" if quick["commands"] else "end_turn", "qfit": quick}).encode()
                return
            # Proposals leave as soon as the model makes them, so the page moves while the explanation is written.
            early: asyncio.Queue = asyncio.Queue()
            task = asyncio.ensure_future(run_qfit(body, on_proposal=early.put_nowait))
            sent = 0
            try:
                while not task.done():
                    waiter = asyncio.ensure_future(early.get())
                    await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
                    if waiter.done():
                        sent += 1
                        yield Event("command", waiter.result()).encode()
                    else:
                        waiter.cancel()
                result, proposals, errors = task.result()
                for error in errors:
                    yield Event("error", error).encode()
                for proposal in proposals[sent:]:
                    yield Event("command", proposal).encode()
                yield Event("text", {"delta": result["message"]}).encode()
                yield Event("sources", [s.get("id") or s.get("url") for s in result["sources"]]).encode()
                yield Event("done", {"stop_reason": "tool_use" if proposals else "end_turn", "qfit": result}).encode()
            except Exception:
                # No prompts, keys or provider exception text are persisted or returned.
                yield Event("error", {"code": "qfit_unavailable", "message": "AI is unavailable. Showing local sources."}).encode()
                result = local_answer(body)
                yield Event("text", {"delta": result["message"]}).encode()
                yield Event("sources", [s["id"] for s in result["sources"]]).encode()
                yield Event("done", {"stop_reason": "error", "qfit": result}).encode()
            finally:
                # CancelledError is a BaseException: a browser abort lands here and cancels the model request.
                if not task.done():
                    task.cancel()

        return StreamingResponse(qfit_stream() if provider == "qfit" else stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    return router
