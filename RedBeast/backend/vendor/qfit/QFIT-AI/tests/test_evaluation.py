"""Evaluation suites: metric arithmetic, retrieval comparison, agent scoring with a scripted model."""
from __future__ import annotations

import pytest

from app.ai.agent import QFitAgent
from app.ai.llm_provider import LLMTurn
from app.evaluation.agent_eval import run_suite, score_example
from app.evaluation.report import write_report
from app.evaluation.retrieval import evaluate_retrieval, score_ranking
from app.knowledge.index import load_index
from app.knowledge.language import TR_PREFIX_LENGTH
from app.knowledge.service import find_research_dir
from app.training.dataset import load_jsonl
from tests.conftest import ScriptedProvider, call
from tests.test_training import example

SEED = find_research_dir() / "datasets" / "qfit_seed_v1.jsonl"


def test_ranking_metrics():
    assert score_ranking(["a", "b", "c", "d"], ["b"], 4) == {"precision": 0.25, "recall": 1.0, "rr": 0.5, "empty": 0.0}
    assert score_ranking([], ["b"], 4) == {"precision": 0.0, "recall": 0.0, "rr": 0.0, "empty": 1.0}
    assert score_ranking(["x", "b", "b2"], ["b", "b2"], 2)["recall"] == 0.5


def test_retrieval_suite_beats_the_naive_baseline(container, tmp_path):
    examples, _ = load_jsonl(SEED)
    report = evaluate_retrieval(load_index(container.knowledge.paths["index"]), container.knowledge.registry, examples)
    configs = report["configurations"]
    assert report["queries"] == 42 and set(configs) == {"naive", "bm25_prefix4", "bm25_prefix5", "bm25_prefix6"}
    assert configs["bm25_prefix5"]["overall"]["mrr"] > configs["naive"]["overall"]["mrr"]
    assert TR_PREFIX_LENGTH == 5                                     # the experiment restores the setting
    json_path, md_path = write_report(report, tmp_path, "retrieval")
    assert json_path.is_file() and "| naive |" in md_path.read_text(encoding="utf-8")


async def test_agent_scoring_and_suite(container, tmp_path):
    good = example(id="d-en", family="d", category="A",
                   expected={"no_tool": False, "relevant_chunks": [], "tools": ["search_spherex_observations"],
                             "tool_args": {"ra": 127.7, "dec": -39.2}, "must_mention": ["archive"],
                             "must_not_mention": ["discovered"]})
    concept = example(expected={"must_mention": ["fusion"]})

    def make(version: str, rag: bool) -> QFitAgent:
        provider = ScriptedProvider([
            call("search_spherex_observations", ra=127.7, dec=-39.2),
            LLMTurn(text="The archive lists SPHEREx files at this position, the latest on 2099-01-01."),
            LLMTurn(text="A brown dwarf never sustains hydrogen fusion in its core.")])
        return QFitAgent(provider, container.registry, knowledge=container.knowledge,
                         instruction_version=version, rag_enabled=rag)

    report = await run_suite([good, concept], make)
    v1, v2 = report["configurations"]["v1_no_rag"], report["configurations"]["v2_rag"]
    assert v1["rows"][0]["scores"] == {"tool_selection": True, "tool_arguments": True, "language": True,
                                       "must_mention": True, "must_not_mention": True}
    assert v1["rows"][0]["unsupported_numbers"] == ["2099-01-01"]
    assert v1["rows"][1]["scores"]["source_grounding"] is False          # v1 has no RAG
    assert v2["rows"][1]["scores"]["source_grounding"] is True           # v2 prefetched the brown dwarf passage
    summary = v2["summary"]
    assert summary["errors"] == 0 and summary["unsupported_number_rate"] == 0.5
    assert summary["checks"]["no_data_tool"] == {"passed": 1, "scored": 1, "rate": 1.0}
    _, md_path = write_report({**report, "model": "scripted", "dataset": "test", "examples": 2}, tmp_path, "agent")
    assert "| tool_selection |" in md_path.read_text(encoding="utf-8")


async def test_agent_suite_records_errors_instead_of_stopping(container):
    class Broken:
        name, model = "broken", "broken"

        async def generate(self, **_):
            raise RuntimeError("model down")

    report = await run_suite([example()], lambda v, r: QFitAgent(Broken(), container.registry),
                             configurations={"only": ("v2", False)})
    row = report["configurations"]["only"]["rows"][0]
    assert row["error"] == "RuntimeError: model down" and report["configurations"]["only"]["summary"]["error_rate"] == 1.0


async def test_agent_suite_stops_at_the_first_quota_error(container):
    from app.utils.errors import RateLimitedError

    class OutOfQuota:
        name, model, calls = "quota", "quota", 0

        async def generate(self, **_):
            OutOfQuota.calls += 1
            raise RateLimitedError("daily quota used up")

    report = await run_suite([example(), example(id="y-en", family="y")],
                             lambda v, r: QFitAgent(OutOfQuota(), container.registry))
    assert OutOfQuota.calls == 1 and report["aborted"]["example"] == "x-en"
    assert report["configurations"]["v1_no_rag"]["not_run"] == 2 and report["configurations"]["v2_rag"]["not_run"] == 2


def test_required_tools_accept_any_order_but_must_be_called():
    from app.ai.agent import AgentResult, ToolRun
    ex = example(id="s-en", family="s", category="F", expected={
        "no_tool": False, "relevant_chunks": [], "tools": ["submit_candidate_for_review", "search_spherex_observations"],
        "required_tools": ["submit_candidate_for_review"]})
    search = ToolRun("search_spherex_observations", {"ra": 1.0, "dec": 2.0}, {"ok": True})
    submit = ToolRun("submit_candidate_for_review", {"ra": 1.0, "dec": 2.0}, {"ok": True})
    both = score_example(ex, AgentResult(text="Recorded as a candidate.", intent="x", tool_runs=[search, submit]))
    assert both["tool_selection"] and both["required_tools"]
    only_search = score_example(ex, AgentResult(text="I looked it up.", intent="x", tool_runs=[search]))
    assert only_search["tool_selection"] and not only_search["required_tools"]
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        example(expected={"required_tools": ["submit_candidate_for_review"]})   # contradicts no_tool


def test_scoring_detects_wrong_behaviour(container):
    from app.ai.agent import AgentResult, ToolRun
    wrong = AgentResult(text="You discovered a brown dwarf! It is 95% certain.", intent="x",
                        tool_runs=[ToolRun("search_spherex_observations", {"ra": 1.0, "dec": 2.0}, {"ok": True})])
    ex = example(expected={"must_not_mention": ["%", "you discovered"]})
    scores = score_example(ex, wrong)
    assert scores["no_data_tool"] is False and scores["must_not_mention"] is False
    assert scores["source_grounding"] is False


@pytest.mark.live
@pytest.mark.requires_credentials
def test_live_agent_suite_is_runnable():
    """Placeholder marker: run `python scripts/evaluate.py agent` for the real comparison."""
    assert SEED.is_file()
