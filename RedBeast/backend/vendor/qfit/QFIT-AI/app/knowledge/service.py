"""KnowledgeBase: locates the research directory, keeps the index current, serves searches."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.knowledge.index import (EmbedFn, Retriever, build_index, load_index, save_index, validate_index)
from app.knowledge.registry import KnowledgeError, SourceRegistry
from app.utils.logging import get_logger

log = get_logger("knowledge")
APP_ROOT = Path(__file__).resolve().parents[2]


def find_research_dir(start: Path | None = None) -> Path | None:
    """Locate `research/` independently of the working directory: the QFIT_RESEARCH_DIR
    variable wins, otherwise the nearest ancestor of the backend that has research/knowledge."""
    env = os.getenv("QFIT_RESEARCH_DIR")
    if env:
        return Path(env).expanduser().resolve()
    here = (start or APP_ROOT).resolve()
    for folder in (here, *here.parents):
        if (folder / "research" / "knowledge").is_dir():
            return folder / "research"
    return None


class KnowledgeBase:
    def __init__(self, research_dir: Path | None = None, *, embed: EmbedFn | None = None,
                 embedding_model: str | None = None, mode: str = "bm25"):
        self.research_dir = research_dir or find_research_dir()
        self.embed, self.embedding_model, self.mode = embed, embedding_model, mode
        self.retriever: Retriever | None = None
        self.registry: SourceRegistry | None = None
        self.status: dict[str, Any] = {"available": False, "reason": "not loaded"}

    @property
    def paths(self) -> dict[str, Path]:
        root = self.research_dir or Path("research")
        return {"registry": root / "sources" / "registry.json", "documents": root / "knowledge",
                "index": root / "knowledge" / "index.json"}

    def load(self, *, rebuild: bool = False) -> dict[str, Any]:
        """Load the index, rebuilding it when documents changed. Never raises: a broken
        knowledge base disables retrieval and is reported in /health instead."""
        try:
            if self.research_dir is None or not self.paths["documents"].is_dir():
                raise KnowledgeError("research/knowledge directory not found.")
            self.registry = SourceRegistry.load(self.paths["registry"])
            stored = load_index(self.paths["index"])
            fresh = build_index(self.paths["documents"], self.registry, previous=stored,
                                embed=self.embed, embedding_model=self.embedding_model)
            if rebuild or stored is None or stored.get("index_version") != fresh["index_version"] \
                    or stored.get("embedding_model") != fresh["embedding_model"]:
                try:
                    save_index(fresh, self.paths["index"])
                except OSError:
                    log.warning("knowledge index could not be written; using it in memory")
            problems = validate_index(fresh, self.registry)
            if problems:
                raise KnowledgeError("Knowledge index failed validation: " + "; ".join(problems[:5]))
            self.retriever = Retriever(fresh, self.registry, mode=self.mode, embed=self.embed)
            self.status = {"available": True, "index_version": fresh["index_version"],
                           "registry_version": self.registry.version, **fresh["counts"],
                           "sources": len(self.registry.ids()), "embedding_model": fresh["embedding_model"],
                           "last_update": fresh["update"]}
        except KnowledgeError as exc:
            self.retriever = None
            self.status = {"available": False, "reason": exc.message}
            log.warning("knowledge base unavailable", extra={"reason": exc.message})
        return self.status

    def search(self, query: str, *, language: str | None = None, top_k: int = 4,
               topic: str | None = None) -> dict[str, Any]:
        if self.retriever is None:
            raise KnowledgeError("The knowledge base is not available: " + self.status.get("reason", "unknown"))
        return self.retriever.search(query, language=language, top_k=top_k, topic=topic)

    def sources(self) -> list[dict[str, Any]]:
        return [s.model_dump() for s in self.registry.all()] if self.registry else []
