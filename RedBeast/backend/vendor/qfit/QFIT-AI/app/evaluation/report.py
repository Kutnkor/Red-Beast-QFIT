"""Write evaluation reports (JSON with every row + a short Markdown summary)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def retrieval_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Retrieval evaluation ({report['created_at']})", "",
             f"Queries: {report['queries']} (dataset {report.get('dataset')}), k = {report['k']}, "
             f"index {report['index_version']}, relevance: {report['relevance']}.", "",
             "| configuration | P@k | R@k | MRR | empty | P@k tr | R@k tr | MRR tr | MRR en |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, cfg in report["configurations"].items():
        o, tr, en = cfg["overall"], cfg["by_language"]["tr"], cfg["by_language"]["en"]
        lines.append(f"| {name} | {o['precision_at_k']} | {o['recall_at_k']} | {o['mrr']} | {o['empty_rate']} | "
                     f"{tr.get('precision_at_k')} | {tr.get('recall_at_k')} | {tr.get('mrr')} | {en.get('mrr')} |")
    lines += ["", f"Best by MRR: **{report['best_by_mrr']}**.", "",
              "P@k is bounded by the number of relevant chunks per query (1-2 here), so with k = 4 it "
              "cannot exceed 0.5. See the dataset manifest for how many examples a person has reviewed."]
    for name, cfg in report["configurations"].items():
        if cfg["misses"]:
            lines += ["", f"Misses ({name}): " + ", ".join(m["id"] for m in cfg["misses"])]
    return "\n".join(lines) + "\n"


def agent_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Agent evaluation ({report['created_at']})", "", f"Model: {report.get('model')}. "
             f"Dataset: {report.get('dataset')} ({report.get('examples')} examples).", "",
             "| check | " + " | ".join(report["configurations"]) + " |",
             "|---|" + "---|" * len(report["configurations"])]
    names = list(report["configurations"])
    checks = report["configurations"][names[0]]["summary"]["checks"]
    for check in checks:
        cells = []
        for name in names:
            c = report["configurations"][name]["summary"]["checks"][check]
            cells.append(f"{c['rate']} ({c['passed']}/{c['scored']})" if c["scored"] else "-")
        lines.append(f"| {check} | " + " | ".join(cells) + " |")
    for key in ("unsupported_number_rate", "mean_unsupported_numbers", "error_rate"):
        lines.append(f"| {key} | " + " | ".join(str(report["configurations"][n]["summary"][key]) for n in names) + " |")
    lines.append("| latency mean / p95 (s) | " + " | ".join(
        f"{report['configurations'][n]['summary']['latency_s']['mean']} / {report['configurations'][n]['summary']['latency_s']['p95']}"
        for n in names) + " |")
    lines.append("| not run | " + " | ".join(str(report["configurations"][n].get("not_run", 0)) for n in names) + " |")
    if report.get("aborted"):
        a = report["aborted"]
        lines += ["", f"**Stopped early** at {a['example']} ({a['configuration']}): {a['reason']}"]
    lines += ["", "Checks are heuristic (keyword and tool-name matching; a negated phrase such as \"not evidence "
              "that you discovered\" still matches a forbidden term): read the rows in the JSON report before "
              "drawing conclusions."]
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], out_dir: Path, kind: str) -> tuple[Path, Path]:
    report.setdefault("created_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{kind}_{_stamp()}"
    json_path, md_path = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md_path.write_text(retrieval_markdown(report) if kind == "retrieval" else agent_markdown(report), encoding="utf-8")
    return json_path, md_path
