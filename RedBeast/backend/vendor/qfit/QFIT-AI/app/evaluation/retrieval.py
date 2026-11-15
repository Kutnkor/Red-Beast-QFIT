"""Retrieval evaluation: does the knowledge search return the passages that answer a question?

Needs no API key and no network. Queries and their relevant chunks come from the example
dataset (every example with `expected.relevant_chunks`). Relevance is strict: a chunk counts
only if its id (document, language, section) is listed.

Metrics per configuration, overall and per language:
  precision@k  share of the top k results that are relevant (averaged over queries)
  recall@k     share of the relevant chunks found in the top k
  MRR          mean of 1 / rank of the first relevant result (0 when none is returned)
  empty_rate   share of queries for which nothing passed the score threshold
"""
from __future__ import annotations

from contextlib import contextmanager
from statistics import mean
from typing import Any, Iterator

from app.knowledge import language as lang_module
from app.knowledge.index import Retriever
from app.training.schema import TrainingExample

CONFIGURATIONS = {
    "naive": {"mode": "naive", "tr_prefix": 5, "description": "raw term overlap, no stemming, no language handling"},
    "bm25_prefix4": {"mode": "bm25", "tr_prefix": 4, "description": "BM25, Turkish words cut to 4 letters"},
    "bm25_prefix5": {"mode": "bm25", "tr_prefix": 5, "description": "BM25, Turkish words cut to 5 letters (default)"},
    "bm25_prefix6": {"mode": "bm25", "tr_prefix": 6, "description": "BM25, Turkish words cut to 6 letters"},
}


@contextmanager
def tr_prefix(length: int) -> Iterator[None]:
    old = lang_module.TR_PREFIX_LENGTH
    lang_module.TR_PREFIX_LENGTH = length
    try:
        yield
    finally:
        lang_module.TR_PREFIX_LENGTH = old


def queries_from(examples: list[TrainingExample]) -> list[dict[str, Any]]:
    return [{"id": e.id, "query": e.input.message, "language": e.language, "category": e.category,
             "relevant": list(e.expected.relevant_chunks)} for e in examples if e.expected.relevant_chunks]


def score_ranking(returned: list[str], relevant: list[str], k: int) -> dict[str, float]:
    top = returned[:k]
    hits = [c for c in top if c in relevant]
    rank = next((i for i, c in enumerate(returned, start=1) if c in relevant), None)
    return {"precision": len(hits) / k, "recall": len(set(hits)) / len(relevant) if relevant else 0.0,
            "rr": 1.0 / rank if rank else 0.0, "empty": float(not returned)}


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"queries": 0}
    return {"queries": len(rows),
            "precision_at_k": round(mean(r["precision"] for r in rows), 3),
            "recall_at_k": round(mean(r["recall"] for r in rows), 3),
            "mrr": round(mean(r["rr"] for r in rows), 3),
            "empty_rate": round(mean(r["empty"] for r in rows), 3)}


def evaluate_retrieval(index: dict[str, Any], registry, examples: list[TrainingExample], *, k: int = 4,
                       configurations: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    queries = queries_from(examples)
    results: dict[str, Any] = {}
    for name, cfg in (configurations or CONFIGURATIONS).items():
        with tr_prefix(cfg["tr_prefix"]):
            retriever = Retriever(index, registry, mode=cfg["mode"])
            rows = []
            for q in queries:
                found = retriever.search(q["query"], language=q["language"], top_k=k)
                returned = [h["chunk_id"] for h in found["hits"]]
                rows.append({**q, "returned": returned, **score_ranking(returned, q["relevant"], k)})
        results[name] = {"description": cfg["description"], "overall": _aggregate(rows),
                         "by_language": {lang: _aggregate([r for r in rows if r["language"] == lang])
                                         for lang in ("en", "tr")},
                         "misses": [{"id": r["id"], "relevant": r["relevant"], "returned": r["returned"]}
                                    for r in rows if r["rr"] == 0.0]}
    best = max(results, key=lambda n: (results[n]["overall"].get("mrr", 0), results[n]["overall"].get("recall_at_k", 0)))
    return {"suite": "retrieval", "k": k, "queries": len(queries), "index_version": index.get("index_version"),
            "relevance": "strict chunk id match", "configurations": results, "best_by_mrr": best}
