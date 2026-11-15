"""Knowledge document parsing and chunking.

A knowledge document is a Markdown file with a small front-matter block and `##`
sections. Each section is one chunk: sections are written to stand alone, so chunking
never cuts a sentence, an equation or a unit away from its context. The last line of
a section lists its sources (`Sources:` / `Kaynaklar:`); an optional `Verification:`
line flags statements that still need a citation.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.knowledge.language import fold

REQUIRED_META = ("id", "title", "language", "topic")
_SOURCES = re.compile(r"^(?:Sources|Kaynaklar)\s*:\s*(.+)$", re.I)
_VERIFY = re.compile(r"^Verification\s*:\s*(.+)$", re.I)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    language: str
    topic: str
    title: str
    heading: str
    text: str
    source_ids: list[str]
    content_hash: str
    path: str
    doc_version: str = "1"
    mission: str | None = None
    data_release: str | None = None
    verification_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParseReport:
    chunks: list[Chunk] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)


def _hash(text: str) -> str:
    return hashlib.sha256(" ".join(fold(text).split()).encode()).hexdigest()[:16]


def parse_document(path: Path, root: Path) -> tuple[list[Chunk], list[str]]:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return [], [f"{rel}: missing front matter"]
    try:
        _, front, body = text.split("---", 2)
    except ValueError:
        return [], [f"{rel}: unterminated front matter"]
    meta = {}
    for line in front.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    errors = [f"{rel}: missing '{k}' in front matter" for k in REQUIRED_META if not meta.get(k)]
    if errors:
        return [], errors
    if meta["language"] not in ("en", "tr"):
        return [], [f"{rel}: unsupported language '{meta['language']}'"]

    chunks: list[Chunk] = []
    for index, section in enumerate(re.split(r"^## +", body, flags=re.M)[1:], start=1):
        lines = section.strip().splitlines()
        heading, content, sources, note = lines[0].strip(), [], [], None
        for line in lines[1:]:
            if match := _SOURCES.match(line.strip()):
                sources = [s.strip() for s in match.group(1).split(",") if s.strip()]
            elif match := _VERIFY.match(line.strip()):
                note = match.group(1).strip()
            else:
                content.append(line)
        body_text = "\n".join(content).strip()
        if not body_text:
            errors.append(f"{rel}: section '{heading}' is empty")
            continue
        if not sources:
            errors.append(f"{rel}: section '{heading}' has no sources")
            continue
        chunks.append(Chunk(
            chunk_id=f"{meta['id']}:{meta['language']}:{index}", doc_id=meta["id"], language=meta["language"],
            topic=meta["topic"], title=meta["title"], heading=heading, text=body_text, source_ids=sources,
            content_hash=_hash(f"{meta['title']}|{heading}|{body_text}|{','.join(sources)}"), path=rel,
            doc_version=meta.get("version", "1"), mission=meta.get("mission"),
            data_release=meta.get("data_release"), verification_note=note))
    if not chunks and not errors:
        errors.append(f"{rel}: no '##' sections found")
    return chunks, errors


def ingest(knowledge_dir: Path, known_sources: set[str]) -> ParseReport:
    """Parse every document, validate provenance and drop exact duplicates."""
    report = ParseReport()
    seen_text: dict[str, str] = {}
    seen_ids: set[str] = set()
    for path in sorted(knowledge_dir.rglob("*.md")):
        chunks, errors = parse_document(path, knowledge_dir)
        report.errors += errors
        for chunk in chunks:
            unknown = [s for s in chunk.source_ids if s not in known_sources]
            if unknown:
                report.errors.append(f"{chunk.path}: section '{chunk.heading}' cites unknown source(s) {unknown}")
                continue
            if chunk.chunk_id in seen_ids:
                report.errors.append(f"{chunk.path}: duplicate chunk id {chunk.chunk_id}")
                continue
            text_key = _hash(chunk.text)
            if text_key in seen_text:
                report.duplicates.append(f"{chunk.chunk_id} duplicates {seen_text[text_key]}")
                continue
            seen_text[text_key] = chunk.chunk_id
            seen_ids.add(chunk.chunk_id)
            report.chunks.append(chunk)
    return report
