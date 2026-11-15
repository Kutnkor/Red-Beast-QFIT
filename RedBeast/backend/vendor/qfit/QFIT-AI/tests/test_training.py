"""Training/evaluation dataset: schema honesty, integrity, leakage-free split, Vertex export."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.knowledge.service import KnowledgeBase, find_research_dir
from app.training.dataset import check_integrity, leakage, load_jsonl, split_by_family
from app.training.schema import CATEGORIES, TrainingExample
from app.training.vertex_export import export, to_vertex_record

SEED = find_research_dir() / "datasets" / "qfit_seed_v1.jsonl"


def example(**over) -> TrainingExample:
    base = {"id": "x-en", "category": "B", "family": "x", "language": "en",
            "input": {"message": "What is a brown dwarf?"},
            "expected": {"behavior": "Answer from the knowledge base.", "no_tool": True,
                         "relevant_chunks": ["brown-dwarfs:en:1"]},
            "label": "concept", "dataset_version": "test"}
    for key, value in over.items():
        base[key] = {**base[key], **value} if isinstance(value, dict) and key in ("input", "expected") else value
    return TrainingExample.model_validate(base)


@pytest.fixture(scope="module")
def references():
    kb = KnowledgeBase()
    kb.load()
    return {"source_ids": kb.registry.ids(), "chunks": {c.chunk_id: c.text for c in kb.retriever.chunks},
            "source_meta": {r.id: f"{r.title}. {r.organization}. {r.publication_date or ''}" for r in kb.registry.all()}}


def test_seed_dataset_passes_integrity(references, container):
    examples, errors = load_jsonl(SEED)
    report = check_integrity(examples, tool_names=container.registry.names(), parse_errors=errors, **references)
    assert report.ok, report.errors
    assert len(examples) == 70 and {e.category for e in examples} == set(CATEGORIES)
    # 68 reviewed by the team on 2026-11-14; the navigation pair was added afterwards by the AI and
    # waits for review. All are synthetic (written, not real conversations).
    pending = {e.id for e in examples if e.annotation_status == "ai_drafted_pending_human_review"}
    assert pending == {"a-take-me-to-en", "a-take-me-to-tr"} and all(e.synthetic for e in examples)
    assert all(e.annotation_status == "human_reviewed" for e in examples if e.id not in pending)
    assert all(not ref.startswith("http") for e in examples for ref in e.source_refs)
    families = {}
    for e in examples:
        families.setdefault(e.family, set()).add(e.language)
    assert all(langs == {"tr", "en"} for langs in families.values())


def test_schema_refuses_dishonest_labels():
    with pytest.raises(ValidationError):
        example(verification_status="expert_verified")
    with pytest.raises(ValidationError):
        example(synthetic=False)
    with pytest.raises(ValidationError):
        example(expected={"tools": ["search_spherex_observations"]})       # no_tool and tools together
    assert example(annotation_status="human_reviewed", verification_status="expert_verified").synthetic


def test_a_cited_source_date_counts_as_evidence(references):
    dated = example(id="d-en", family="d", source_refs=["jpl-identity-crisis"],
                    expected={"relevant_chunks": ["brown-dwarfs:en:2"],
                              "reference_answer": "JPL (2003) gives 10 to 70 Jupiter masses."})
    assert check_integrity([dated], **references).errors == []
    undated = example(id="u-en", family="u", source_refs=[], expected={
        "relevant_chunks": ["brown-dwarfs:en:2"], "reference_answer": "JPL (2003) gives 10 to 70 Jupiter masses."})
    assert any("['2003']" in e for e in check_integrity([undated], **references).errors)


def test_integrity_errors(references):
    bad = [example(), example(id="x-en"),                                   # duplicate id, same language
           example(id="y-tr", family="y", language="tr", source_refs=["nope"],
                   expected={"relevant_chunks": ["nope:tr:1"],
                             "reference_answer": "Brown dwarfs weigh 42 Jupiter masses."})]
    report = check_integrity(bad, tool_names=["search_spherex_observations"], **references)
    text = " | ".join(report.errors)
    assert "duplicate id x-en" in text and "family x: 2 examples in 'en'" in text
    assert "unknown source 'nope'" in text and "unknown knowledge chunk 'nope:tr:1'" in text
    assert "numbers not in its evidence: ['42']" in text
    assert any("no translation pair" in w for w in report.warnings)


def test_split_keeps_families_together_and_is_deterministic():
    examples, _ = load_jsonl(SEED)
    first, second = split_by_family(examples), split_by_family(examples)
    assert {k: [e.id for e in v] for k, v in first.items()} == {k: [e.id for e in v] for k, v in second.items()}
    assert leakage(first) == [] and sum(map(len, first.values())) == len(examples)
    for split in ("validation", "test"):
        assert {e.category for e in first[split]} == set(CATEGORIES)     # every category is evaluated
    other = split_by_family(examples, seed="another")
    assert [e.id for e in other["test"]] != [e.id for e in first["test"]]


def test_vertex_export_only_takes_reviewed_examples(tmp_path):
    reviewed = example(id="r-en", family="r", annotation_status="human_reviewed",
                       expected={"reference_answer": "A brown dwarf never sustains hydrogen fusion."})
    tool = example(id="t-en", family="t", category="A", annotation_status="human_validated",
                   expected={"no_tool": False, "relevant_chunks": [], "tools": ["search_spherex_observations"],
                             "tool_args": {"ra": 10.0, "dec": 20.0}})
    report = export([example(), reviewed, tool], tmp_path / "out.jsonl",
                    tool_declarations=[{"name": "search_spherex_observations", "description": "d", "parameters": {}}])
    assert report["written"] == 2 and report["skipped"] == {"not_human_reviewed": 1, "no_learnable_target": 0}
    assert report["uploaded"] is False
    lines = [json.loads(line) for line in (tmp_path / "out.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[0]["contents"][-1] == {"role": "model", "parts": [{"text": "A brown dwarf never sustains hydrogen fusion."}]}
    assert lines[1]["contents"][-1]["parts"][0]["functionCall"] == {"name": "search_spherex_observations",
                                                                   "args": {"ra": 10.0, "dec": 20.0}}
    assert "tools" in lines[1] and "RESPONSE LANGUAGE: English" in lines[0]["systemInstruction"]["parts"][0]["text"]
    assert to_vertex_record(example()) is None                         # nothing to learn from
    assert export([example()], tmp_path / "all.jsonl", include_unreviewed=True)["skipped"]["no_learnable_target"] == 1
