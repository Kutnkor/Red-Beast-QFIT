"""Provider-neutral LLM interface. The agent and the astronomy layer only know this;
swapping Gemini for another model means writing one new class."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None  # provider-native message, replayed verbatim on the next request


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(self, *, system: str, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]]) -> LLMTurn:
        """messages: {"role": "user"|"assistant"|"tool", ...} in conversation order.
        tools: [{"name", "description", "parameters": <JSON schema>}]."""
        ...
