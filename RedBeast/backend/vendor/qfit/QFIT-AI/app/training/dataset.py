"""Load, check, split and describe a Q-FIT example dataset (JSONL).

Integrity rules (errors stop the pipeline, warnings are reported):
  - every line parses and matches the schema; ids are unique
  - source_refs exist in the source registry; relevant_chunks exist in the knowledge index
  - expected tools exist in the tool registry
  - a family has one category and at most one example per language
  - every number in a reference_answer occurs in the input or in the cited knowledge
    chunks (the same grounding check the assistant's answers go through)
Splits are made by family, so a Turkish example and its English twin never end up on
opposite sides of the train/test boundary (no translation leakage).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from app.ai.grounding import unsupported_numbers
from app.training.schema import CATEGORIES, SPLITS, TrainingExample

DEFAULT_RATIOS = {"train": 0.7, "validation": 0.15, "test": 0.15}


@dataclass
class IntegrityReport:
    examples: list[TrainingExample] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "examples": len(self.examples), "errors": self.errors, "warnings": self.warnings}


def load_jsonl(path: Path) -> tuple[list[TrainingExample], list[str]]:
    examples, errors = [], []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            examples.append(TrainingExample.model_validate(json.loads(line)))
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: not valid JSON ({exc.msg})")
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'example'}: {e['msg']}" for e in exc.errors()[:4])
            errors.append(f"line {number}: {problems}")
    return examples, errors


def check_integrity(examples: list[TrainingExample], *, source_ids: Iterable[str] = (),
                    chunks: dict[str, str] | None = None, tool_names: Iterable[str] | None = None,
                    parse_errors: list[str] | None = None,
                    source_meta: dict[str, str] | None = None) -> IntegrityReport:
    """`chunks` maps chunk id -> text. `source_meta` maps source id -> its citation text (title,
    organization, publication date): a reference answer may state what its cited sources say
    about themselves, e.g. "JPL (2003)". Checks that need a reference set are skipped when it is empty."""
    source_meta = source_meta or {}
    report = IntegrityReport(examples=examples, errors=list(parse_errors or []))
    sources, tools, chunks = set(source_ids), set(tool_names or []), chunks or {}
    ids = Counter(e.id for e in examples)
    report.errors += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    families: dict[str, list[TrainingExample]] = defaultdict(list)
    for e in examples:
        families[e.family].append(e)
        if sources:
            report.errors += [f"{e.id}: unknown source '{s}'" for s in e.source_refs if s not in sources]
        if chunks:
            report.errors += [f"{e.id}: unknown knowledge chunk '{c}'" for c in e.expected.relevant_chunks
                              if c not in chunks]
        if tools:
            report.errors += [f"{e.id}: unknown tool '{t}'" for t in e.expected.tools + e.expected.required_tools
                              if t not in tools]
        if e.category == "B" and not e.expected.relevant_chunks:
            report.warnings.append(f"{e.id}: conceptual example without relevant_chunks cannot score retrieval")
        if e.expected.reference_answer:
            evidence = [e.input.message, json.dumps(e.input.context or {})]
            evidence += [chunks[c] for c in e.expected.relevant_chunks if c in chunks]
            evidence += [source_meta[s] for s in e.source_refs if s in source_meta]
            missing = unsupported_numbers(e.expected.reference_answer, evidence)
            if missing:
                report.errors.append(f"{e.id}: reference_answer has numbers not in its evidence: {missing}")
    for name, members in families.items():
        if len({m.category for m in members}) > 1:
            report.errors.append(f"family {name}: members have different categories")
        langs = Counter(m.language for m in members)
        report.errors += [f"family {name}: {n} examples in '{lang}'" for lang, n in langs.items() if n > 1]
        if len(langs) == 1:
            report.warnings.append(f"family {name}: only '{next(iter(langs))}', no translation pair")
    report.warnings += [f"category {c} ({CATEGORIES[c]}) has no examples" for c in CATEGORIES
                        if not any(e.category == c for e in examples)]
    return report


def _bucket(family: str, seed: str) -> float:
    digest = hashlib.sha256(f"{seed}:{family}".encode()).hexdigest()
    return int(digest[:12], 16) / float(16 ** 12)


def split_by_family(examples: list[TrainingExample], ratios: dict[str, float] | None = None,
                    seed: str = "qfit") -> dict[str, list[TrainingExample]]:
    """Deterministic split. Families are stratified by category: within each category the
    families are ordered by a seeded hash and cut by the ratios, so every split sees every
    category when there are enough families."""
    ratios = ratios or DEFAULT_RATIOS
    total = sum(ratios.values())
    by_category: dict[str, list[str]] = defaultdict(list)
    for e in examples:
        if e.family not in by_category[e.category]:
            by_category[e.category].append(e.family)
    assignment: dict[str, str] = {}
    for category, families in by_category.items():
        ordered = sorted(families, key=lambda f: _bucket(f, seed))
        n = len(ordered)
        n_test = round(n * ratios["test"] / total) if n >= 3 else 0
        n_val = round(n * ratios["validation"] / total) if n >= 3 else 0
        n_test, n_val = max(n_test, 1 if n >= 3 else 0), max(n_val, 1 if n >= 3 else 0)
        for i, family in enumerate(ordered):
            assignment[family] = "test" if i < n_test else "validation" if i < n_test + n_val else "train"
    out: dict[str, list[TrainingExample]] = {s: [] for s in SPLITS}
    for e in examples:
        out[assignment[e.family]].append(e)
    return out


def leakage(splits: dict[str, list[TrainingExample]]) -> list[str]:
    """Families or identical inputs that appear in more than one split."""
    seen: dict[str, str] = {}
    problems = []
    for split, items in splits.items():
        for e in items:
            for key in (f"family:{e.family}", f"input:{' '.join(e.input.message.lower().split())}"):
                if key in seen and seen[key] != split:
                    problems.append(f"{key} in {seen[key]} and {split}")
                seen.setdefault(key, split)
    return problems


def manifest(splits: dict[str, list[TrainingExample]], *, dataset_path: Path, report: IntegrityReport,
             seed: str, versions: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dataset_path.read_bytes()
    all_examples = [e for items in splits.values() for e in items]
    return {
        "dataset": dataset_path.name,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "dataset_versions": sorted({e.dataset_version for e in all_examples}),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split_method": "by family, stratified by category, seeded sha256 order",
        "seed": seed,
        "counts": {s: len(items) for s, items in splits.items()},
        "families": {s: len({e.family for e in items}) for s, items in splits.items()},
        "by_category": {s: dict(sorted(Counter(e.category for e in items).items())) for s, items in splits.items()},
        "by_language": {s: dict(sorted(Counter(e.language for e in items).items())) for s, items in splits.items()},
        "annotation_status": dict(Counter(e.annotation_status for e in all_examples)),
        "verification_status": dict(Counter(e.verification_status for e in all_examples)),
        "synthetic": sum(e.synthetic for e in all_examples),
        "leakage": leakage(splits),
        "integrity": report.to_dict(),
        "versions": versions or {},
        "note": "Examples labelled ai_drafted_pending_human_review have not been checked by a person.",
    }


def write_splits(splits: dict[str, list[TrainingExample]], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for split, items in splits.items():
        path = out_dir / f"{split}.jsonl"
        path.write_text("".join(json.dumps(e.model_dump(), ensure_ascii=False) + "\n" for e in items), encoding="utf-8")
        paths[split] = path
    return paths
