"""Export examples to the JSONL layout used by Vertex AI supervised tuning of Gemini.

Nothing here uploads data or starts a tuning job. Fine-tuning is not available through the
Gemini Developer API / AI Studio; it exists only on Vertex AI and is billed. This exporter is
kept so the team can use the dataset later without rewriting it. Check the record layout
against the current Vertex AI documentation before uploading: the format is versioned by Google.

Record layout (one per line):
  {"systemInstruction": {"role": "system", "parts": [{"text": ...}]},
   "contents": [{"role": "user", "parts": [{"text": ...}]},
                {"role": "model", "parts": [{"text": ...}] | [{"functionCall": {...}}]}],
   "tools": [{"functionDeclarations": [...]}]}           # only for tool-call examples
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.ai.prompts import build_system_prompt, render_user_message
from app.training.schema import TrainingExample

REVIEWED = ("human_reviewed", "human_validated")


def to_vertex_record(example: TrainingExample, *, instruction_version: str = "v2",
                     tool_declarations: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """One example -> one record, or None when the example has no target the model could learn."""
    exp = example.expected
    if exp.reference_answer:
        model_parts: list[dict[str, Any]] = [{"text": exp.reference_answer}]
    elif exp.tools:
        model_parts = [{"functionCall": {"name": exp.tools[0], "args": exp.tool_args}}]
    else:
        return None
    level = (example.input.context or {}).get("expertise_level")
    contents = [{"role": "user" if t["role"] == "user" else "model", "parts": [{"text": t["content"]}]}
                for t in example.input.history]
    contents.append({"role": "user", "parts": [{"text": render_user_message(example.input.message, example.input.context)}]})
    contents.append({"role": "model", "parts": model_parts})
    record: dict[str, Any] = {
        "systemInstruction": {"role": "system", "parts": [{"text": build_system_prompt(
            instruction_version, example.language, level)}]},
        "contents": contents}
    if "functionCall" in model_parts[0] and tool_declarations:
        record["tools"] = [{"functionDeclarations": tool_declarations}]
    return record


def export(examples: list[TrainingExample], out_path: Path, *, include_unreviewed: bool = False,
           instruction_version: str = "v2", tool_declarations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Write the records and return a report of what was written and what was skipped and why."""
    written, skipped = 0, {"not_human_reviewed": 0, "no_learnable_target": 0}
    lines = []
    for example in examples:
        if example.annotation_status not in REVIEWED and not include_unreviewed:
            skipped["not_human_reviewed"] += 1
            continue
        record = to_vertex_record(example, instruction_version=instruction_version,
                                  tool_declarations=tool_declarations)
        if record is None:
            skipped["no_learnable_target"] += 1
            continue
        lines.append(json.dumps(record, ensure_ascii=False))
        written += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {"file": out_path.name, "written": written, "skipped": skipped,
            "include_unreviewed": include_unreviewed, "instruction_version": instruction_version,
            "uploaded": False, "note": "Export only. Vertex AI tuning is a paid service and was not run."}
