"""Loader for the project's scientific configuration, `research/data.json`.

The file is owned by the whole team and is the single source of truth for phase
descriptions and classification thresholds. Its schema was not available when this
module was written, so the loader is deliberately schema-agnostic: it locates the
file, loads it safely, versions it, and reports structural problems. It never repairs
or guesses a value. Schema-specific accessors and the deterministic threshold
evaluator are added on top once the real file is in the repository.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.utils.logging import get_logger

log = get_logger("scientific_config")
APP_ROOT = Path(__file__).resolve().parents[2]
_VERSION_KEYS = ("version", "config_version", "schema_version", "data_version")
_LANGS = ("tr", "en")


def find_config_path(start: Path | None = None) -> Path | None:
    env = os.getenv("QFIT_SCIENTIFIC_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    here = (start or APP_ROOT).resolve()
    for folder in (here, *here.parents):
        candidate = folder / "research" / "data.json"
        if candidate.is_file():
            return candidate
    return None


def _walk(node: Any, path: str = ""):
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}[{i}]")


def inspect_structure(data: Any) -> dict[str, Any]:
    """Schema-independent checks. Findings are reported, never fixed."""
    problems: list[str] = []
    bilingual = 0
    for path, node in _walk(data):
        if not isinstance(node, dict):
            continue
        keys = {str(k).lower() for k in node}
        present = [lang for lang in _LANGS if lang in keys]
        if len(present) == 2:
            bilingual += 1
            for lang in _LANGS:
                value = next(v for k, v in node.items() if str(k).lower() == lang)
                if isinstance(value, str) and not value.strip():
                    problems.append(f"{path}: empty '{lang}' text")
        elif len(present) == 1 and all(isinstance(v, str) for v in node.values()):
            problems.append(f"{path}: has '{present[0]}' text but no '{[l for l in _LANGS if l != present[0]][0]}' text")
        for stem in {k[:-4] for k in node if isinstance(k, str) and k.endswith("_min")}:
            low, high = node.get(f"{stem}_min"), node.get(f"{stem}_max")
            if isinstance(low, (int, float)) and isinstance(high, (int, float)) and low > high:
                problems.append(f"{path}: {stem}_min ({low}) is greater than {stem}_max ({high})")
        if isinstance(node.get("min"), (int, float)) and isinstance(node.get("max"), (int, float)) \
                and node["min"] > node["max"]:
            problems.append(f"{path}: min ({node['min']}) is greater than max ({node['max']})")
        for key, value in node.items():
            if "threshold" in str(key).lower() and isinstance(value, str):
                problems.append(f"{path}.{key}: threshold is text, expected a number")
    return {"bilingual_nodes": bilingual, "problems": problems}


class ScientificConfig:
    def __init__(self, path: Path | None = None):
        self._explicit = path
        self._data: Any = None
        self._stamp: tuple[float, int] | None = None
        self._status: dict[str, Any] = {"status": "missing"}

    @property
    def path(self) -> Path | None:
        return self._explicit or find_config_path()

    def load(self, *, force: bool = False) -> dict[str, Any]:
        """Load or reload. Re-reads the file only when it changed on disk or `force` is set."""
        path = self.path
        if path is None or not path.is_file():
            self._data, self._stamp = None, None
            self._status = {"status": "missing", "message": "research/data.json was not found. Phase "
                            "descriptions and threshold evaluation are unavailable until it is provided."}
            return self._status
        stat = path.stat()
        stamp = (stat.st_mtime, stat.st_size)
        if not force and stamp == self._stamp:
            return self._status
        raw = path.read_bytes()                      # read-only: the original file is never written
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            where = f" (line {exc.lineno}, column {exc.colno})" if isinstance(exc, json.JSONDecodeError) else ""
            self._data, self._stamp = None, stamp
            self._status = {"status": "invalid", "message": f"research/data.json is not valid JSON{where}."}
            log.error("scientific config invalid", extra={"detail": self._status["message"]})
            return self._status
        declared = next((str(data[k]) for k in _VERSION_KEYS if isinstance(data, dict) and k in data), None)
        digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
        report = inspect_structure(data)
        self._data, self._stamp = data, stamp
        self._status = {
            "status": "loaded", "file": path.name,
            "configuration_version": f"{declared}+{digest}" if declared else f"sha256:{digest}",
            "declared_version": declared, "content_hash": digest,
            "top_level_keys": sorted(map(str, data)) if isinstance(data, dict) else [],
            "bilingual_nodes": report["bilingual_nodes"], "problems": report["problems"][:50],
            "problem_count": len(report["problems"]),
        }
        return self._status

    def status(self) -> dict[str, Any]:
        return self.load()

    @property
    def version(self) -> str | None:
        return self.load().get("configuration_version")

    def get(self, dotted_path: str, default: Any = None) -> Any:
        """Read a value by dotted path, e.g. 'phases.main_sequence'. No value is ever invented."""
        self.load()
        node = self._data
        for part in filter(None, dotted_path.split(".")):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                return default
        return node

    @staticmethod
    def localized(node: Any, language: str) -> Any:
        """Pick the text for one language from {'tr': ..., 'en': ...}. Returns None when
        that language is missing: the caller must report it, never fall back silently."""
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).lower() == language:
                    return value
        return None
