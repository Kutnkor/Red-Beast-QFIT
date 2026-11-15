"""Agent evaluation: run the real agent on the example dataset and score its behaviour.

With Gemini this needs GEMINI_API_KEY and network access (the data tools query IRSA, SIMBAD
and Horizons). The scoring itself is deterministic and is unit-tested with a scripted provider.

Per example (only the checks the example defines are scored):
  tool_selection   the first tool called is one of expected.tools
  tool_arguments   the first call contains expected.tool_args (numbers within 1e-3)
  required_tools   every tool in expected.required_tools was called at some point
  no_data_tool     for expected.no_tool: no tool other than search_knowledge_base was called
  language         the answer is in the example's language (heuristic detector)
  must_mention     every listed term occurs (case and Turkish diacritics folded)
  must_not_mention none of the listed terms occurs
  source_grounding a relevant knowledge chunk reached the model (prefetch or tool call)
Run-level: share of answers with unsupported numbers, mean unsupported numbers per answer,
latency (mean, p95), error rate. Two configurations are compared by default: v1 without
RAG (the baseline) and v2 with RAG.
"""
from __future__ import annotations

import time
from statistics import mean
from typing import Any, Awaitable, Callable

from app.knowledge.language import detect_language, fold
from app.training.schema import TrainingExample

KNOWLEDGE_TOOL = "search_knowledge_base"
CHECKS = ("tool_selection", "tool_arguments", "required_tools", "no_data_tool", "language", "must_mention",
          "must_not_mention", "source_grounding")
AgentFactory = Callable[[str, bool], Any]          # (instruction_version, rag_enabled) -> QFitAgent
DEFAULT_CONFIGURATIONS = {"v1_no_rag": ("v1", False), "v2_rag": ("v2", True)}


def _args_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    for key, value in expected.items():
        got = actual.get(key)
        if isinstance(value, (int, float)) and isinstance(got, (int, float)):
            if abs(float(value) - float(got)) > 1e-3:
                return False
        elif got != value:
            return False
    return True


def score_example(example: TrainingExample, result: Any) -> dict[str, bool]:
    """`result` is an AgentResult. Returns {check: passed} for the checks this example defines."""
    exp, scores = example.expected, {}
    calls = [(r.name, r.args) for r in result.tool_runs]
    data_calls = [c for c in calls if c[0] != KNOWLEDGE_TOOL]
    if exp.tools:
        scores["tool_selection"] = bool(calls) and calls[0][0] in exp.tools
        if exp.tool_args:
            first = next((args for name, args in calls if name in exp.tools), None)
            scores["tool_arguments"] = first is not None and _args_match(exp.tool_args, first)
    if exp.required_tools:
        called = {name for name, _ in calls}
        scores["required_tools"] = all(tool in called for tool in exp.required_tools)
    if exp.no_tool:
        scores["no_data_tool"] = not data_calls
    clarified = bool(calls) and calls[-1][0] == "request_clarification"
    if result.text and not clarified:
        scores["language"] = detect_language(result.text, default="unknown") == example.language
    text = fold(result.text or "")
    if exp.must_mention:
        scores["must_mention"] = all(fold(term) in text for term in exp.must_mention)
    if exp.must_not_mention:
        scores["must_not_mention"] = not any(fold(term) in text for term in exp.must_not_mention)
    if exp.relevant_chunks:
        seen = {h["chunk_id"] for h in result.knowledge_hits}
        for run in result.tool_runs:
            if run.name == KNOWLEDGE_TOOL and run.outcome.get("ok"):
                seen |= {h["chunk_id"] for h in run.outcome["result"]["hits"]}
        scores["source_grounding"] = bool(seen & set(exp.relevant_chunks))
    return scores


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))] if ordered else 0.0


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    done = [r for r in rows if r["error"] is None]
    checks = {}
    for check in CHECKS:
        values = [r["scores"][check] for r in done if check in r["scores"]]
        checks[check] = {"passed": sum(values), "scored": len(values),
                         "rate": round(sum(values) / len(values), 3) if values else None}
    latencies = [r["latency_s"] for r in done]
    return {"examples": len(rows), "errors": len(rows) - len(done),
            "error_rate": round((len(rows) - len(done)) / len(rows), 3) if rows else None,
            "checks": checks,
            "answers_with_unsupported_numbers": sum(1 for r in done if r["unsupported_numbers"]),
            "unsupported_number_rate": round(sum(1 for r in done if r["unsupported_numbers"]) / len(done), 3) if done else None,
            "mean_unsupported_numbers": round(mean(len(r["unsupported_numbers"]) for r in done), 3) if done else None,
            "latency_s": {"mean": round(mean(latencies), 2) if latencies else None, "p95": round(_p95(latencies), 2)},
            "by_category": {cat: sum(all(r["scores"].values()) for r in done if r["category"] == cat)
                            for cat in sorted({r["category"] for r in rows})},
            "note": "by_category counts examples that passed every check they define."}


async def run_suite(examples: list[TrainingExample], make_agent: AgentFactory, *,
                    configurations: dict[str, tuple[str, bool]] | None = None,
                    on_progress: Callable[[str, int, int], Awaitable[None] | None] | None = None) -> dict[str, Any]:
    """Stops at the first rate-limit / quota error: retrying would only burn more quota, and a
    report made of quota errors measures nothing. Unrun examples are counted, not scored."""
    from app.utils.errors import RateLimitedError
    report: dict[str, Any] = {"suite": "agent", "configurations": {}, "aborted": None}
    for name, (version, rag) in (configurations or DEFAULT_CONFIGURATIONS).items():
        if report["aborted"]:
            report["configurations"][name] = {"instruction_version": version, "rag_enabled": rag,
                                              "summary": summarise([]), "rows": [], "not_run": len(examples)}
            continue
        agent = make_agent(version, rag)
        rows = []
        for number, example in enumerate(examples, start=1):
            started = time.monotonic()
            row = {"id": example.id, "category": example.category, "language": example.language, "error": None,
                   "scores": {}, "unsupported_numbers": [], "tools_called": []}
            try:
                result = await agent.run(example.input.message, example.input.history, example.input.context)
                row.update(scores=score_example(example, result), unsupported_numbers=result.unsupported_numbers,
                           tools_called=[r.name for r in result.tool_runs], answer=result.text,
                           timings=result.timings)
            except RateLimitedError as exc:
                report["aborted"] = {"configuration": name, "example": example.id, "reason": exc.message}
            except Exception as exc:                     # an evaluation records failures, it does not stop
                row["error"] = f"{type(exc).__name__}: {getattr(exc, 'message', str(exc))[:200]}"
            if report["aborted"]:
                break
            row["latency_s"] = round(time.monotonic() - started, 3)
            rows.append(row)
            if on_progress:
                maybe = on_progress(name, number, len(examples))
                if maybe is not None:
                    await maybe
        report["configurations"][name] = {"instruction_version": version, "rag_enabled": rag,
                                          "summary": summarise(rows), "rows": rows,
                                          "not_run": len(examples) - len(rows)}
    return report
