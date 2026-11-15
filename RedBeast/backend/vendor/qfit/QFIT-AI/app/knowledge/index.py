"""Knowledge index: build, persist, load and search.

Retrieval technology. The corpus is small (tens of short, curated chunks in two
languages), so a vector database would add an operational dependency and no accuracy.
The index is a JSON file searched with BM25 over language-aware tokens (Turkish
diacritic folding and prefix stemming, English suffix stemming). Embeddings are an
optional second signal: when an embedding function is supplied their cosine score is
blended with BM25. The index is rebuilt incrementally and is fully reproducible from
the documents and the registry.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from app.knowledge.documents import Chunk, ingest
from app.knowledge.language import detect_language, tokenize
from app.knowledge.registry import KnowledgeError, SourceRegistry

INDEX_FORMAT = 1
EmbedFn = Callable[[Sequence[str]], list[list[float]]]


def _version(chunks: Sequence[Chunk], registry_version: str) -> str:
    digest = hashlib.sha256((registry_version + "|" + "|".join(sorted(c.content_hash for c in chunks))).encode())
    return digest.hexdigest()[:12]


def _embedding_text(chunk: Chunk) -> str:
    return f"{chunk.title}. {chunk.heading}. {chunk.text}"


def build_index(knowledge_dir: Path, registry: SourceRegistry, *, previous: dict[str, Any] | None = None,
                embed: EmbedFn | None = None, embedding_model: str | None = None) -> dict[str, Any]:
    """Build the index. Unchanged chunks keep their embeddings (incremental update)."""
    report = ingest(knowledge_dir, set(registry.ids()))
    if report.errors:
        raise KnowledgeError("Knowledge base validation failed: " + "; ".join(report.errors[:8]),
                             details={"errors": report.errors})
    old_chunks = {c["chunk_id"]: c for c in (previous or {}).get("chunks", [])}
    old_vectors = (previous or {}).get("embeddings", {}) if (previous or {}).get("embedding_model") == embedding_model else {}
    stats = {"added": [], "changed": [], "unchanged": [], "removed": sorted(set(old_chunks) - {c.chunk_id for c in report.chunks})}
    embeddings: dict[str, list[float]] = {}
    pending: list[Chunk] = []
    for chunk in report.chunks:
        old = old_chunks.get(chunk.chunk_id)
        state = "added" if old is None else ("unchanged" if old["content_hash"] == chunk.content_hash else "changed")
        stats[state].append(chunk.chunk_id)
        if embed is not None:
            if state == "unchanged" and chunk.chunk_id in old_vectors:
                embeddings[chunk.chunk_id] = old_vectors[chunk.chunk_id]
            else:
                pending.append(chunk)
    if embed is not None and pending:
        vectors = embed([_embedding_text(c) for c in pending])
        if len(vectors) != len(pending):
            raise KnowledgeError("Embedding function returned the wrong number of vectors.")
        embeddings.update({c.chunk_id: list(map(float, v)) for c, v in zip(pending, vectors)})
    return {
        "format": INDEX_FORMAT,
        "index_version": _version(report.chunks, registry.version),
        "registry_version": registry.version,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chunking": {"unit": "markdown '##' section", "tokenizer": "fold+stem (tr prefix-5, en suffix)"},
        "embedding_model": embedding_model if embed is not None else None,
        "counts": {"chunks": len(report.chunks), "documents": len({(c.doc_id, c.language) for c in report.chunks}),
                   "by_language": dict(Counter(c.language for c in report.chunks))},
        "update": {k: len(v) for k, v in stats.items()},
        "duplicates_skipped": report.duplicates,
        "chunks": [c.to_dict() for c in report.chunks],
        "embeddings": embeddings,
    }


def save_index(index: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


def load_index(path: Path) -> dict[str, Any] | None:
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return index if index.get("format") == INDEX_FORMAT and isinstance(index.get("chunks"), list) else None


def validate_index(index: dict[str, Any], registry: SourceRegistry) -> list[str]:
    """Integrity check used at start-up and in tests."""
    problems = []
    chunks = [Chunk(**c) for c in index.get("chunks", [])]
    if index.get("index_version") != _version(chunks, index.get("registry_version", "")):
        problems.append("index_version does not match the chunk hashes (index edited by hand?)")
    for chunk in chunks:
        missing = [s for s in chunk.source_ids if registry.get(s) is None]
        if missing:
            problems.append(f"{chunk.chunk_id}: unknown sources {missing}")
    return problems


class Retriever:
    """BM25 retriever with optional embedding blend. `mode='naive'` is the evaluation
    baseline: raw term overlap, no stemming, no language handling."""

    def __init__(self, index: dict[str, Any], registry: SourceRegistry, *, mode: str = "bm25",
                 embed: EmbedFn | None = None):
        self.registry = registry
        self.mode = mode
        self.embed = embed if index.get("embeddings") else None
        self.index_version = index.get("index_version", "unknown")
        self.chunks = [Chunk(**c) for c in index["chunks"]]
        self.vectors = index.get("embeddings", {})
        advanced = mode != "naive"
        self._tokens = [tokenize(f"{c.title} {c.heading} {c.heading} {c.text}", c.language,
                                 stemming=advanced, stopwords=advanced) for c in self.chunks]
        self._tf = [Counter(t) for t in self._tokens]
        self._df = Counter(term for tf in self._tf for term in tf)
        self._avg_len = (sum(map(len, self._tokens)) / len(self._tokens)) if self._tokens else 1.0
        # Heading match: a short question like "What is SPHEREx?" reduces to one very common term,
        # so BM25 alone stays below the threshold although a section is titled exactly that.
        self._heading_sets = [set(tokenize(c.heading, c.language)) if advanced else set() for c in self.chunks]

    HEADING_BONUS = 3.0

    def _heading_bonus(self, query_tokens: list[str], i: int) -> float:
        heading = self._heading_sets[i]
        return self.HEADING_BONUS if heading and heading <= set(query_tokens) else 0.0

    def _bm25(self, query_tokens: list[str], i: int, k1: float = 1.5, b: float = 0.75) -> float:
        score, n, length = 0.0, len(self.chunks), len(self._tokens[i])
        for term in set(query_tokens):
            freq = self._tf[i].get(term)
            if not freq:
                continue
            idf = math.log(1 + (n - self._df[term] + 0.5) / (self._df[term] + 0.5))
            score += idf * freq * (k1 + 1) / (freq + k1 * (1 - b + b * length / self._avg_len))
        return score

    def search(self, query: str, *, language: str | None = None, top_k: int = 4, topic: str | None = None,
               min_score: float = 3.0) -> dict[str, Any]:
        language = language or detect_language(query)
        if self.mode == "naive":
            q = tokenize(query, "en", stemming=False, stopwords=False)
            scored = [(float(sum(1 for t in set(q) if t in self._tf[i])), i) for i in range(len(self.chunks))]
            ranked = sorted((s for s in scored if s[0] > 0), key=lambda s: (-s[0], s[1]))[:top_k]
            return self._result(query, language, ranked, False)

        def rank(lang: str | None) -> list[tuple[float, int]]:
            scored = []
            for i, chunk in enumerate(self.chunks):
                if (lang and chunk.language != lang) or (topic and chunk.topic != topic):
                    continue
                query_tokens = tokenize(query, chunk.language)
                score = self._bm25(query_tokens, i)
                if score > 0:
                    score += self._heading_bonus(query_tokens, i)
                    scored.append((score, i))
            return sorted(scored, key=lambda s: (-s[0], s[1]))

        ranked = rank(language)
        fallback = False
        if not ranked or ranked[0][0] < min_score:
            other = rank(None)                       # nothing in the user's language: try every language
            if other and (not ranked or other[0][0] > ranked[0][0]):
                ranked, fallback = other, True
        if self.embed is not None and ranked:
            ranked = self._blend(query, ranked)
        ranked = [s for s in ranked if s[0] >= min_score][:top_k] if self.embed is None else ranked[:top_k]
        return self._result(query, language, ranked, fallback)

    def _blend(self, query: str, ranked: list[tuple[float, int]]) -> list[tuple[float, int]]:
        qv = self.embed([query])[0]
        qn = math.sqrt(sum(x * x for x in qv)) or 1.0
        top = ranked[0][0] or 1.0
        out = []
        for score, i in ranked:
            v = self.vectors.get(self.chunks[i].chunk_id)
            cosine = 0.0
            if v:
                cosine = sum(a * b for a, b in zip(qv, v)) / (qn * (math.sqrt(sum(x * x for x in v)) or 1.0))
            out.append((0.5 * score / top * top + 0.5 * max(cosine, 0.0) * top, i))
        return sorted(out, key=lambda s: (-s[0], s[1]))

    def _result(self, query: str, language: str, ranked: list[tuple[float, int]], fallback: bool) -> dict[str, Any]:
        hits = []
        for score, i in ranked:
            c = self.chunks[i]
            sources = sorted((self.registry.get(s) for s in c.source_ids if self.registry.get(s)),
                             key=lambda r: self.registry.rank(r.id))
            hits.append({"chunk_id": c.chunk_id, "doc_id": c.doc_id, "language": c.language, "topic": c.topic,
                         "title": c.title, "heading": c.heading, "text": c.text, "score": round(score, 3),
                         "data_release": c.data_release, "verification_note": c.verification_note,
                         "sources": [s.citation() for s in sources]})
        return {"query": query, "language": language, "index_version": self.index_version,
                "retriever": self.mode + ("+embeddings" if self.embed else ""),
                "other_language_used": fallback, "count": len(hits), "hits": hits}
