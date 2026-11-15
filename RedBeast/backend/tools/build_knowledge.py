"""Build a deterministic, source-hashed knowledge bundle. No provider is contacted."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "backend" / "blinkspace" / "knowledge"


def sections(text: str):
    current, lines = "intro", []
    for line in text.splitlines():
        if line.startswith("## "):
            if lines:
                yield current, "\n".join(lines).strip()
            heading = line[3:].strip()
            number = re.match(r"(\d+)\.", heading)
            current = number[1] if number else re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
            lines = [line]
        else:
            lines.append(line)
    if lines:
        yield current, "\n".join(lines).strip()


def build(root: Path = ROOT):
    sources = [("method", "docs/METHOD.md"), ("data-sources", "docs/DATA_SOURCES.md"), ("features", "docs/FEATURES.md"),
               ("motion", "backend/blinkspace/knowledge/motion.md"), ("epistemic", "backend/blinkspace/knowledge/epistemic.md"),
               ("stellar-models", "docs/STELLAR_MODELS.md")]
    sources += [(f"report:{p.stem}", p.relative_to(root).as_posix()) for p in sorted((root / "reports" / "targets").glob("*.md"))]
    chunks = []
    for document, relative in sources:
        path = root / relative
        content = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode()).hexdigest()
        for section, body in sections(content):
            # Bound retrieval chunks without padding or duplicating content to hit a token quota.
            pieces = [body[i:i + 6000] for i in range(0, len(body), 6000)]
            for index, piece in enumerate(pieces):
                suffix = f"-{index + 1}" if len(pieces) > 1 else ""
                chunks.append({"id": f"{document}#{section}{suffix}", "document_id": document, "source": relative,
                               "source_sha256": digest, "verification": "source_document_only", "text": piece})
    return {"schema_version": 1, "notice": "Source documents retain their original dates; inclusion is not a new verification.",
            "chunks": chunks, "utf8_bytes": sum(len(chunk["text"].encode()) for chunk in chunks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=KNOWLEDGE / "bundle.json")
    args = parser.parse_args()
    bundle = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(bundle['chunks'])} source-hashed chunks ({bundle['utf8_bytes']} UTF-8 text bytes).")


if __name__ == "__main__":
    main()
