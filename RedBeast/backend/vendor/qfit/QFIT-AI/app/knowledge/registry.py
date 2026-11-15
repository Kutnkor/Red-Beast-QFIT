"""Scientific source registry: every knowledge item must point at one of these records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.utils.errors import QFitError


class KnowledgeError(QFitError):
    code, status_code = "knowledge_base_error", 500


class SourceRecord(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9\-]*$")
    title: str = Field(..., min_length=3)
    url: str = Field(..., min_length=8)
    organization: str
    reliability: str
    topic: str
    publication_date: str | None = None
    retrieval_date: str
    document_version: str | None = None
    language: str = "en"
    mission: str | None = None
    data_release: str | None = None
    note: str | None = None

    def citation(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.title, "url": self.url, "organization": self.organization,
                "reliability": self.reliability, "publication_date": self.publication_date,
                "retrieval_date": self.retrieval_date, "data_release": self.data_release, "note": self.note}


class SourceRegistry:
    def __init__(self, version: str, reliability_order: list[str], sources: list[SourceRecord]):
        self.version = version
        self.reliability_order = reliability_order
        self._by_id = {s.id: s for s in sources}

    @classmethod
    def load(cls, path: Path) -> "SourceRegistry":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KnowledgeError(f"Source registry not found: {path.name}") from exc
        except json.JSONDecodeError as exc:
            raise KnowledgeError(f"Source registry is not valid JSON (line {exc.lineno}).") from exc
        try:
            sources = [SourceRecord.model_validate(item) for item in raw["sources"]]
        except (KeyError, TypeError, ValidationError) as exc:
            raise KnowledgeError(f"Source registry has an invalid record: {str(exc)[:200]}") from exc
        ids = [s.id for s in sources]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise KnowledgeError(f"Duplicate source ids in registry: {', '.join(duplicates)}")
        order = raw.get("reliability_order", [])
        unknown = sorted({s.reliability for s in sources} - set(order))
        if unknown:
            raise KnowledgeError(f"Reliability categories missing from reliability_order: {', '.join(unknown)}")
        return cls(str(raw.get("registry_version", "unversioned")), order, sources)

    def get(self, source_id: str) -> SourceRecord | None:
        return self._by_id.get(source_id)

    def ids(self) -> list[str]:
        return list(self._by_id)

    def all(self) -> list[SourceRecord]:
        return list(self._by_id.values())

    def rank(self, source_id: str) -> int:
        record = self._by_id.get(source_id)
        return self.reliability_order.index(record.reliability) if record else len(self.reliability_order)
