"""Google Gemini provider (official `google-genai` SDK, function calling)."""
from __future__ import annotations

from typing import Any

from app.ai.llm_provider import LLMTurn, ToolCall
from app.utils.errors import AIUnavailableError, RateLimitedError, UpstreamError
from app.utils.logging import get_logger

log = get_logger("gemini")


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, *, timeout_seconds: float = 60, client: Any = None):
        from google import genai
        from google.genai import types
        self._types = types
        self.model = model
        self._client = client or genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)))

    # ------------------------------------------------------------ conversion
    def _contents(self, messages: list[dict[str, Any]]) -> list[Any]:
        types = self._types
        contents: list[Any] = []
        pending: list[Any] = []  # consecutive tool results travel in one user turn

        def flush() -> None:
            if pending:
                contents.append(types.Content(role="user", parts=list(pending)))
                pending.clear()

        for message in messages:
            role = message["role"]
            if role == "tool":
                pending.append(types.Part.from_function_response(
                    name=message["name"], response={"result": message["result"]}))
                continue
            flush()
            if role == "assistant":
                # Replay the model's own message untouched: it carries the function-call
                # parts (and thought signatures) the API expects to see again.
                contents.append(message.get("raw") or types.Content(
                    role="model", parts=[types.Part(text=message.get("content") or "")]))
            else:
                contents.append(types.Content(role="user", parts=[types.Part(text=message["content"])]))
        flush()
        return contents

    def _config(self, system: str, tools: list[dict[str, Any]]) -> Any:
        types = self._types
        declarations = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                                  parameters_json_schema=t["parameters"]) for t in tools]
        return types.GenerateContentConfig(
            system_instruction=system, temperature=0.2,
            tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))

    # --------------------------------------------------------------- request
    async def generate(self, *, system: str, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]]) -> LLMTurn:
        from google.genai import errors
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=self._contents(messages), config=self._config(system, tools))
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            daily = code == 429 and "per day" in str(getattr(exc, "message", "") or "").lower()
            log.warning(f"gemini api error {code} {status}", extra={"status": code, "api_status": status,
                                                                    "daily_quota": daily})
            if code == 429:
                if daily:
                    raise RateLimitedError("The daily Gemini API quota for this key is used up. It resets once a "
                                           "day; a paid tier or another model raises the limit.",
                                           details={"http_status": 429, "quota": "per_day"}) from exc
                raise RateLimitedError("The Gemini API rate limit or quota was reached. Try again shortly.",
                                       details={"http_status": 429}) from exc
            if code in (401, 403):
                raise AIUnavailableError("The Gemini API rejected the configured API key.") from exc
            if code == 404:
                raise AIUnavailableError(f"Gemini model '{self.model}' is not available. "
                                         "Check GEMINI_MODEL.") from exc
            raise UpstreamError(f"The Gemini API returned an error (HTTP {code}{', ' + status if status else ''}).",
                                details={"http_status": code}) from exc
        except Exception as exc:
            log.warning("gemini request failed", extra={"error": type(exc).__name__})
            raise UpstreamError(f"The Gemini API could not be reached ({type(exc).__name__}).") from exc
        return self._parse(response)

    @staticmethod
    def _parse(response: Any) -> LLMTurn:
        candidates = getattr(response, "candidates", None) or []
        content = candidates[0].content if candidates else None
        texts, calls = [], []
        for part in (getattr(content, "parts", None) or []):
            call = getattr(part, "function_call", None)
            if call is not None and call.name:
                calls.append(ToolCall(name=call.name, args=dict(call.args or {}), id=getattr(call, "id", None)))
            elif getattr(part, "text", None) and not getattr(part, "thought", False):
                texts.append(part.text)
        return LLMTurn(text="".join(texts).strip(), tool_calls=calls, raw=content)
