"""The Q-FIT agent: a provider-neutral tool-calling loop."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.ai.grounding import unsupported_numbers
from app.ai.llm_provider import LLMProvider
from app.ai.prompts import DEFAULT_INSTRUCTION_VERSION, build_system_prompt, render_user_message
from app.ai.tool_registry import ToolRegistry
from app.knowledge.language import detect_language
from app.services import response_builder as rb
from app.utils.errors import QFitError
from app.utils.logging import get_logger

log = get_logger("agent")
_LIST_KEYS = ("observations", "image_products", "spectral_products", "objects", "periods",
              "candidates", "samples", "products")
_HEAVY_KEYS = ("footprint", "cloud_access", "extra", "publisher_did", "sources", "download_check")
_MAX_ITEMS_FOR_MODEL = 8


def compact_for_model(value: Any) -> Any:
    """Shrink a tool result before it is sent back to the model: the full result still
    goes to the client, the model only needs enough to describe it."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in _HEAVY_KEYS:
                continue
            if key in _LIST_KEYS and isinstance(item, list) and len(item) > _MAX_ITEMS_FOR_MODEL:
                out[key] = [compact_for_model(i) for i in item[:_MAX_ITEMS_FOR_MODEL]]
                out[f"{key}_omitted_from_this_view"] = len(item) - _MAX_ITEMS_FOR_MODEL
            else:
                out[key] = compact_for_model(item)
        return out
    if isinstance(value, list):
        return [compact_for_model(i) for i in value]
    return value


@dataclass
class ToolRun:
    name: str
    args: dict[str, Any]
    outcome: dict[str, Any]  # {"ok": True, "result": ...} | {"ok": False, "error": ...}


@dataclass
class AgentResult:
    text: str
    intent: str
    tool_runs: list[ToolRun] = field(default_factory=list)
    parts: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    language: str = "en"
    instruction_version: str = DEFAULT_INSTRUCTION_VERSION
    knowledge_hits: list[dict[str, Any]] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    timings: list[dict[str, Any]] = field(default_factory=list)   # one entry per model call / tool batch


class QFitAgent:
    def __init__(self, provider: LLMProvider, registry: ToolRegistry, max_steps: int = 6, *,
                 knowledge=None, instruction_version: str = DEFAULT_INSTRUCTION_VERSION,
                 rag_enabled: bool = True, rag_top_k: int = 4):
        self.provider = provider
        self.registry = registry
        self.max_steps = max_steps
        self.knowledge = knowledge
        self.instruction_version = instruction_version
        self.rag_enabled = rag_enabled and instruction_version != "v1"   # v1 is the no-RAG baseline
        self.rag_top_k = rag_top_k

    async def _timed(self, call) -> tuple[dict[str, Any], int]:
        started = time.monotonic()
        outcome = await self.registry.execute(call.name, call.args)
        return outcome, round((time.monotonic() - started) * 1000)

    def _prefetch(self, message: str, language: str) -> dict[str, Any] | None:
        """Retrieve knowledge passages before the first model call (RAG)."""
        if not self.rag_enabled or self.knowledge is None:
            return None
        try:
            return self.knowledge.search(message, language=language, top_k=self.rag_top_k)
        except QFitError as exc:
            log.warning("knowledge prefetch failed", extra={"reason": exc.message})
            return None

    async def run(self, message: str, history: list[dict[str, str]] | None = None,
                  context: dict[str, Any] | None = None) -> AgentResult:
        context = context or {}
        language = context.get("locale") or detect_language(message)
        prefetched = self._prefetch(message, language)
        hits = prefetched["hits"] if prefetched else []
        messages: list[dict[str, Any]] = [{"role": h["role"], "content": h["content"]}
                                          for h in (history or [])]
        messages.append({"role": "user", "content": render_user_message(message, context, knowledge=hits)})
        system = build_system_prompt(self.instruction_version, language, context.get("expertise_level"))
        tools = self.registry.declarations()
        runs: list[ToolRun] = []
        text, clarified = "", False

        timings: list[dict[str, Any]] = []
        for step in range(self.max_steps):
            started = time.monotonic()
            turn = await self.provider.generate(system=system, messages=messages, tools=tools)
            timings.append({"step": step, "kind": "model", "ms": round((time.monotonic() - started) * 1000),
                            "tool_calls": [c.name for c in turn.tool_calls]})
            if not turn.tool_calls:
                text = turn.text
                break
            messages.append({"role": "assistant", "content": turn.text, "raw": turn.raw})
            # Tool calls of one model turn are independent: run them concurrently, keep their order.
            started = time.monotonic()
            outcomes = await asyncio.gather(*(self._timed(call) for call in turn.tool_calls))
            timings.append({"step": step, "kind": "tools", "ms": round((time.monotonic() - started) * 1000),
                            "tools": [{"name": c.name, "ms": ms} for c, (_, ms) in zip(turn.tool_calls, outcomes)]})
            for call, (outcome, ms) in zip(turn.tool_calls, outcomes):
                runs.append(ToolRun(call.name, call.args, outcome))
                log.info("tool call", extra={"tool": call.name, "ok": outcome["ok"], "step": step, "ms": ms})
                messages.append({"role": "tool", "name": call.name, "call_id": call.id,
                                 "result": compact_for_model(outcome)})
                if call.name == "request_clarification" and outcome["ok"]:
                    clarified, text = True, outcome["result"]["question"]
            if clarified:
                break
        else:
            text = ("I retrieved the data shown here but could not finish summarising it within "
                    "the allowed number of steps.")

        result = self._assemble(text, runs, prefetched)
        result.language, result.instruction_version, result.knowledge_hits = language, self.instruction_version, hits
        result.timings = timings
        result.parts["data"]["timing"] = {
            "model_calls": sum(1 for t in timings if t["kind"] == "model"),
            "model_ms": sum(t["ms"] for t in timings if t["kind"] == "model"),
            "tools_ms": sum(t["ms"] for t in timings if t["kind"] == "tools")}
        result.parts["language"] = language
        if not clarified:
            self._check_grounding(result, message, history, context)
        return result

    @staticmethod
    def _check_grounding(result: AgentResult, message: str, history: list[dict[str, str]] | None,
                         context: dict[str, Any]) -> None:
        """Flag numbers in the model's text that occur in none of the evidence it was given."""
        evidence = [message, json.dumps(context, default=str)] + [h["content"] for h in (history or [])]
        evidence += [json.dumps(r.outcome, default=str, ensure_ascii=False) for r in result.tool_runs]
        evidence += [h["text"] for h in result.knowledge_hits]
        missing = unsupported_numbers(result.text, evidence)
        result.unsupported_numbers = missing
        result.parts["data"]["grounding"] = {"checked": True, "unsupported_numbers": missing}
        if missing:
            result.parts["uncertainty"].append(
                "These numbers in the explanation were not found in the retrieved data or knowledge "
                f"passages and are unverified: {', '.join(missing)}.")

    def _assemble(self, text: str, runs: list[ToolRun], prefetched: dict[str, Any] | None = None) -> AgentResult:
        partials, intent, errors = [], "conversation", []
        if prefetched and prefetched["hits"]:
            partials.append(rb.from_knowledge(prefetched))   # evidence and sources; keeps intent unchanged
        for run in runs:
            tool = self.registry.get(run.name)
            if not run.outcome["ok"] or tool is None:
                errors.append({"tool": run.name, **run.outcome.get("error", {})})
                continue
            part = tool.presenter(run.outcome["result"])
            partials.append(part)
            intent = part["intent"]
        parts = rb.merge(partials)
        if errors:
            parts["data"]["tool_errors"] = errors
            if intent == "conversation":  # no tool succeeded: tell the frontend
                intent = "error"
                parts["actions"].append({"type": "show_error", "payload": {
                    "code": errors[-1].get("code", "tool_error"), "message": errors[-1].get("message", "")}})
        if not text:
            text = partials[-1]["message"] if partials else "I could not produce an answer for that request."
        for error in errors:
            parts["uncertainty"].append(f"Tool {error['tool']} failed: {error.get('message', 'unknown error')}")
        return AgentResult(text=text, intent=intent, tool_runs=runs, parts=parts,
                           model=getattr(self.provider, "model", None))
