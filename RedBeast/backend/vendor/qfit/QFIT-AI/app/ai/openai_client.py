"""OpenAI provider: the Responses API with function calling, over plain HTTPS (no SDK).

The Responses API is used because newer reasoning models (for example gpt-6-astra) reject
function tools in /v1/chat/completions while reasoning is on. The model's output items,
including its reasoning items, are replayed verbatim on the next request, as the API expects.

The key stays on the server (OPENAI_API_KEY in .env); it is never sent to the browser and
never appears in logs or error messages. A ChatGPT subscription does not include API usage:
the key must come from platform.openai.com with billing enabled.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.ai.llm_provider import LLMTurn, ToolCall
from app.utils.errors import AIUnavailableError, RateLimitedError, UpstreamError
from app.utils.logging import get_logger

log = get_logger("openai")


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, *, base_url: str = "https://api.openai.com/v1",
                 timeout_seconds: float = 60, transport: httpx.AsyncBaseTransport | None = None,
                 reasoning_effort: str = ""):
        if not model:
            raise AIUnavailableError("LLM_PROVIDER is 'openai' but OPENAI_MODEL is empty.")
        self.model = model
        self.reasoning_effort = reasoning_effort.strip()
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport,
                                         headers={"Authorization": f"Bearer {api_key}"})

    @staticmethod
    def _input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            role = message["role"]
            if role == "tool":
                items.append({"type": "function_call_output", "call_id": message.get("call_id") or message["name"],
                              "output": json.dumps(message["result"], ensure_ascii=False, default=str)})
            elif role == "assistant":
                raw = message.get("raw")
                if isinstance(raw, list):              # the model's own output items, replayed untouched
                    items.extend(raw)
                else:
                    items.append({"role": "assistant", "content": message.get("content") or ""})
            else:
                items.append({"role": "user", "content": message["content"]})
        return items

    @staticmethod
    def _tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"type": "function", "name": t["name"], "description": t["description"],
                 "parameters": t["parameters"]} for t in tools]

    async def generate(self, *, system: str, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]]) -> LLMTurn:
        # No temperature: reasoning models only accept the default and reject the request otherwise.
        body: dict[str, Any] = {"model": self.model, "instructions": system, "input": self._input(messages)}
        if tools:
            body["tools"] = self._tools(tools)
        if self.reasoning_effort:      # supported values depend on the model (see docs/MODEL_EVALUATION.md)
            body["reasoning"] = {"effort": self.reasoning_effort}
        try:
            response = await self._client.post(f"{self.base_url}/responses", json=body)
        except httpx.TimeoutException as exc:
            raise UpstreamError("The OpenAI API did not answer in time.") from exc
        except httpx.HTTPError as exc:
            log.warning("openai unreachable", extra={"error": type(exc).__name__})
            raise UpstreamError(f"The OpenAI API could not be reached ({type(exc).__name__}).") from exc
        if response.status_code >= 400:
            self._raise(response)
        try:
            return self._parse(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise UpstreamError("The OpenAI API returned an unreadable response.") from exc

    def _raise(self, response: httpx.Response) -> None:
        code = response.status_code
        try:
            error = response.json().get("error") or {}
        except ValueError:
            error = {}
        kind = error.get("code") or error.get("type") or ""
        log.warning(f"openai api error {code} {kind}", extra={"status": code, "api_code": kind,
                                                               "param": error.get("param")})
        if code == 401:
            raise AIUnavailableError("The OpenAI API rejected the configured API key.")
        if code == 429 and kind == "insufficient_quota":
            raise RateLimitedError("The OpenAI account has no API credit left. Check billing at platform.openai.com.",
                                   details={"http_status": 429, "quota": "billing"})
        if code == 429:
            raise RateLimitedError("The OpenAI API rate limit was reached. Try again shortly.",
                                   details={"http_status": 429})
        if code == 404 or kind == "model_not_found":
            raise AIUnavailableError(f"OpenAI model '{self.model}' is not available to this key. Check OPENAI_MODEL.")
        param = f", parameter {error['param']}" if error.get("param") else ""
        raise UpstreamError(f"The OpenAI API returned an error (HTTP {code}{', ' + kind if kind else ''}{param}).",
                            details={"http_status": code})

    @staticmethod
    def _parse(payload: dict[str, Any]) -> LLMTurn:
        output = payload["output"]
        texts, calls = [], []
        for item in output:
            kind = item.get("type")
            if kind == "message":
                texts += [part.get("text", "") for part in item.get("content") or []
                          if part.get("type") == "output_text"]
            elif kind == "function_call" and item.get("name"):
                raw_args = item.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except json.JSONDecodeError:
                    args = {"_unparsed_arguments": raw_args}   # fails validation and goes back to the model
                calls.append(ToolCall(name=item["name"], args=args, id=item.get("call_id")))
        return LLMTurn(text="".join(texts).strip(), tool_calls=calls, raw=output)

    async def aclose(self) -> None:
        await self._client.aclose()
