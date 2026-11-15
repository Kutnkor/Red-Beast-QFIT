"""Knowledge base: language handling, ingestion, provenance checks, incremental index, retrieval."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.knowledge.documents import ingest, parse_document
from app.knowledge.index import Retriever, build_index, validate_index
from app.knowledge.language import detect_language, fold, stem, tokenize
from app.knowledge.registry import KnowledgeError, SourceRegistry
from app.knowledge.service import KnowledgeBase, find_research_dir

RESEARCH = find_research_dir()
DOC = """---
id: test-doc
title: Test document
language: en
topic: testing
---
## First section
Brown dwarfs glow in the infrared.
Sources: qfit-spec

## Second section
Spectral images cover one detector band.
Sources: spherex-data-products
"""


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    base = KnowledgeBase()
    assert base.load()["available"] is True, base.status
    return base


@pytest.fixture
def corpus(tmp_path) -> Path:
    """A private research dir: the registry is real, the documents are written by the test."""
    (tmp_path / "sources").mkdir()
    shutil.copy(RESEARCH / "sources" / "registry.json", tmp_path / "sources" / "registry.json")
    (tmp_path / "knowledge" / "en").mkdir(parents=True)
    (tmp_path / "knowledge" / "en" / "test.md").write_text(DOC, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("text,expected", [
    ("Kahverengi cüce nedir?", "tr"), ("SPHEREx hangi dalga boylarını gözlüyor?", "tr"),
    ("kahverengi cuce nedir", "tr"), ("What is a brown dwarf?", "en"), ("Show me M31", "en"), ("", "en"),
    ("Vega'ya git.", "tr"), ("Sirius'a götür", "tr"), ("Beni Betelgeuse yıldızına götür.", "tr"),
    ("Take me to Vega's neighbourhood", "en"), ("Show me M31's data", "en"),
])
def test_language_detection(text, expected):
    assert detect_language(text) == expected


def test_folding_stemming_and_stopwords():
    assert fold("CÜCE IŞIK İzmir") == "cuce isik izmir"
    assert stem(fold("gözlemlerini"), "tr") == "gozle" and stem("bant", "tr") == "bant"
    assert stem("observations", "en") == "observation" and stem("dwarfs", "en") == "dwarf"
    assert tokenize("The brown dwarfs", "en") == ["brown", "dwarf"]
    assert tokenize("0.75 micron", "en") == ["0.75", "micron"]


def test_real_corpus_ingests_cleanly_with_provenance():
    registry = SourceRegistry.load(RESEARCH / "sources" / "registry.json")
    report = ingest(RESEARCH / "knowledge", set(registry.ids()))
    assert report.errors == [] and len(report.chunks) == 82
    assert {c.language for c in report.chunks} == {"en", "tr"}
    assert all(c.source_ids for c in report.chunks)
    # every English section has a Turkish twin with the same id position
    ids = {c.chunk_id for c in report.chunks}
    assert all(c.chunk_id.replace(":en:", ":tr:") in ids for c in report.chunks if c.language == "en")


def test_documents_without_provenance_are_rejected(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("no front matter", encoding="utf-8")
    assert parse_document(bad, tmp_path)[1] == ["bad.md: missing front matter"]
    bad.write_text(DOC.replace("Sources: qfit-spec\n", ""), encoding="utf-8")
    chunks, errors = parse_document(bad, tmp_path)
    assert len(chunks) == 1 and "has no sources" in errors[0]
    bad.write_text(DOC.replace("qfit-spec", "made-up-source"), encoding="utf-8")
    report = ingest(tmp_path, {"qfit-spec", "spherex-data-products"})
    assert any("unknown source" in e for e in report.errors)


def test_duplicate_text_is_skipped(tmp_path):
    (tmp_path / "a.md").write_text(DOC, encoding="utf-8")
    (tmp_path / "b.md").write_text(DOC.replace("id: test-doc", "id: copy"), encoding="utf-8")
    report = ingest(tmp_path, {"qfit-spec", "spherex-data-products"})
    assert len(report.chunks) == 2 and len(report.duplicates) == 2


def test_incremental_index_and_tamper_detection(corpus):
    registry = SourceRegistry.load(corpus / "sources" / "registry.json")
    calls = []

    def embed(texts):
        calls.append(len(texts))
        return [[1.0, float(len(t))] for t in texts]

    first = build_index(corpus / "knowledge", registry, embed=embed, embedding_model="fake")
    assert first["update"] == {"added": 2, "changed": 0, "unchanged": 0, "removed": 0} and calls == [2]
    doc = corpus / "knowledge" / "en" / "test.md"
    doc.write_text(DOC.replace("glow in the infrared", "emit mostly infrared light"), encoding="utf-8")
    second = build_index(corpus / "knowledge", registry, previous=first, embed=embed, embedding_model="fake")
    assert second["update"]["changed"] == 1 and second["update"]["unchanged"] == 1 and calls == [2, 1]
    assert second["index_version"] != first["index_version"] and validate_index(second, registry) == []
    tampered = json.loads(json.dumps(second))
    tampered["chunks"][0]["content_hash"] = "0" * 16
    assert any("does not match" in p for p in validate_index(tampered, registry))


def test_knowledge_base_reports_a_missing_directory(tmp_path):
    kb = KnowledgeBase(tmp_path / "nowhere")
    assert kb.load() == {"available": False, "reason": "research/knowledge directory not found."}
    with pytest.raises(KnowledgeError):
        kb.search("brown dwarf")


def test_knowledge_base_writes_its_index(corpus):
    kb = KnowledgeBase(corpus)
    status = kb.load()
    assert status["available"] and status["chunks"] == 2 and (corpus / "knowledge" / "index.json").is_file()


@pytest.mark.parametrize("query,language,expected", [
    ("What is a brown dwarf?", "en", "brown-dwarfs:en:1"),
    ("Kahverengi cüce nedir?", "tr", "brown-dwarfs:tr:1"),
    ("kahverengi cuce nedir", "tr", "brown-dwarfs:tr:1"),
    ("SPHEREx detector bands wavelength", "en", "spherex-data-products:en:3"),
    ("Tayfsal çözme gücü nedir", "tr", "spectroscopy:tr:2"),
])
def test_retrieval_finds_the_answering_passage(kb, query, language, expected):
    result = kb.search(query, language=language)
    assert result["hits"] and result["hits"][0]["chunk_id"] == expected
    assert result["hits"][0]["sources"] and all(s["url"].startswith("http") for s in result["hits"][0]["sources"])
    assert result["retriever"] == "bm25" and result["index_version"] == kb.status["index_version"]


@pytest.mark.parametrize("query,language,expected", [("What is SPHEREx?", "en", "spherex-mission:en:1"),
                                                     ("SPHEREx nedir?", "tr", "spherex-mission:tr:1")])
def test_short_questions_match_a_section_heading(kb, query, language, expected):
    # one very common term scores below the BM25 threshold; the heading match lifts it
    assert kb.search(query, language=language)["hits"][0]["chunk_id"] == expected


def test_retrieval_filters_and_thresholds(kb):
    topic = kb.search("mass range", language="en", topic="brown_dwarfs")
    assert topic["hits"] and {h["topic"] for h in topic["hits"]} == {"brown_dwarfs"}
    assert kb.search("pizza recipe with mozzarella", language="en")["hits"] == []
    naive = Retriever({"chunks": [c.to_dict() for c in kb.retriever.chunks], "index_version": "x"},
                      kb.registry, mode="naive")
    assert naive.search("brown dwarf", language="en")["retriever"] == "naive"
