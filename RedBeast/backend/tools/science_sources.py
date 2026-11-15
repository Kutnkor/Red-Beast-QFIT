"""Reproducible, checksum-recorded source downloads for the catalogue builders."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from blinkspace.targets import RESOURCES

SOURCE_DIR = RESOURCES / "source_data"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_json(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
        stream.write(text)
        temporary = stream.name
    # These are public scientific resources, also read by an unprivileged image
    # runtime after Docker COPY; NamedTemporaryFile otherwise leaves mode 0600.
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def source_bytes(name: str, url: str, *, adql: str | None = None, refresh: bool = False) -> tuple[bytes, dict]:
    """Use an exact cached response only when the request URL/query also match."""
    path = SOURCE_DIR / name
    manifest_path = path.with_suffix(path.suffix + ".provenance.json")
    if not refresh and path.exists() and manifest_path.exists():
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        data = path.read_bytes()
        if meta.get("url") == url and meta.get("adql") == adql and meta.get("sha256") == sha256(data):
            return data, meta
    params = None if adql is None else urlencode({"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql}).encode()
    request = Request(url, data=params, headers={"User-Agent": "BlinkSpace-scientific-data-builder/1.0"})
    with urlopen(request, timeout=240) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "")
    if adql and (b"QUERY_STATUS\" value=\"ERROR" in data or data.lstrip().startswith(b"<?xml") or "html" in content_type):
        raise RuntimeError(f"TAP returned non-CSV error for {name}: {data[:500]!r}")
    meta = {"url": url, "adql": adql, "retrieved_utc": utc_now(), "sha256": sha256(data), "bytes": len(data)}
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    write_json(manifest_path, meta)
    print(f"{name}: {len(data)} bytes, SHA-256 {meta['sha256']}", flush=True)
    return data, meta


def tap_csv(name: str, endpoint: str, adql: str, *, refresh: bool = False) -> tuple[list[dict], dict]:
    data, meta = source_bytes(name, endpoint, adql=adql, refresh=refresh)
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")))), meta


def finite(value):
    import math
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None
