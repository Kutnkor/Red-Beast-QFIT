"""Ollama provider: a local open-weight model with tool calling, through Ollama's /api/chat.

No API key and no quota. Quality depends on the model chosen: small local models pick tools
and follow the evidence rules less reliably than Gemini, so measure with
`python scripts/evaluate.py agent --provider ollama` before relying on one.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.ai.llm_provider import LLMTurn, ToolCall
from app.utils.errors import AIUnavailableError, UpstreamError
from app.utils.logging import get_logger

log = get_logger("ollama")
_THINK = re.compile(r"<think>.*?</think>", re.S)


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, *, timeout_seconds: float = 120,
                 transport: httpx.AsyncBaseTransport | None = None):
        if not model:
            raise AIUnavailableError("LLM_PROVIDER is 'ollama' but OLLAMA_MODEL is empty.")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport)

    @staticmethod
    def _messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for message in messages:
            role = message["role"]
            if role == "tool":
                out.append({"role": "tool", "tool_name": message["name"],
                            "content": json.dumps(message["result"], ensure_ascii=False, default=str)})
            elif role == "assistant":
                # Replay the model's own message, including its tool_calls.
                out.append(message.get("raw") or {"role": "assistant", "content": message.get("content") or ""})
            else:
                out.append({"role": "user", "content": message["content"]})
        return out

    @staticmethod
    def _tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                  "parameters": t["parameters"]}} for t in tools]

    async def generate(self, *, system: str, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]]) -> LLMTurn:
        body: dict[str, Any] = {"model": self.model, "messages": self._messages(system, messages),
                                "stream": False, "options": {"temperature": 0.2}}
        if tools:
            body["tools"] = self._tools(tools)
        try:
            response = await self._client.post(f"{self.base_url}/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise UpstreamError("The local Ollama model did not answer in time.") from exc
        except httpx.HTTPError as exc:
            log.warning("ollama unreachable", extra={"error": type(exc).__name__})
            raise AIUnavailableError(f"Ollama is not reachable at {self.base_url}. Is the Ollama app running?") from exc
        if response.status_code == 404:
            raise AIUnavailableError(f"Ollama has no model '{self.model}'. Run: ollama pull {self.model}")
        if response.status_code >= 400:
            log.warning(f"ollama error {response.status_code}", extra={"status": response.status_code})
            raise UpstreamError(f"Ollama returned an error (HTTP {response.status_code}).",
                                details={"http_status": response.status_code})
        try:
            return self._parse(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise UpstreamError("Ollama returned an unreadable response.") from exc

    @staticmethod
    def _parse(payload: dict[str, Any]) -> LLMTurn:
        message = payload["message"]
        calls = []
        for i, call in enumerate(message.get("tool_calls") or []):
            function = call.get("function", {})
            args = function.get("arguments") or {}
            if isinstance(args, str):                    # some models return the arguments as JSON text
                args = json.loads(args) if args.strip() else {}
            if function.get("name"):
                calls.append(ToolCall(name=function["name"], args=dict(args), id=call.get("id") or f"call-{i}"))
        text = _THINK.sub("", message.get("content") or "").strip()
        raw = {"role": "assistant", "content": message.get("content") or ""}
        if message.get("tool_calls"):
            raw["tool_calls"] = message["tool_calls"]
        return LLMTurn(text=text, tool_calls=calls, raw=raw)

    async def aclose(self) -> None:
        await self._client.aclose()
