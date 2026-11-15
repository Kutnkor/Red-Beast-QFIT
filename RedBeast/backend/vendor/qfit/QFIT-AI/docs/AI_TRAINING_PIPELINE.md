# AI training pipeline

## What "training" means here

Q-FIT does **not** fine-tune or train model weights. Say "we built a knowledge base, retrieval,
instructions and an evaluation", never "we trained the model".

Why:
- Fine-tuning is not available through the Gemini Developer API / Google AI Studio (removed in May 2025;
  registry source `google-aistudio-tuning`). It exists only on Vertex AI, which is billed
  (`google-vertex-tuning`).
- The project's failure modes (invented numbers, catalog match mistaken for an observation, candidate
  called a discovery) are better addressed by retrieval, tool design and rules that can be measured and
  rolled back, than by weights nobody can inspect.

What is trained, in the broad sense:

| Layer | Where | Changed by |
|---|---|---|
| Knowledge | `research/knowledge/{en,tr}/*.md` + `research/sources/registry.json` | Editing documents; the index rebuilds itself |
| Retrieval | `app/knowledge/` | Code; measured by the retrieval suite |
| Instructions | `app/ai/prompts.py` (`v1`, `v2`) | New version + agent suite comparison |
| Tools | `app/ai/tool_registry.py` | Code + tests |
| Evaluation data | `research/datasets/*.jsonl` | People reviewing examples |

## Example format

One JSON object per line, schema `app/training/schema.py`:

```json
{"id": "e-mass-range-tr", "category": "E", "family": "e-mass-range", "language": "tr",
 "input": {"message": "Kahverengi cücelerin kütle aralığı nedir?", "context": null, "history": []},
 "expected": {"behavior": "Sources disagree on the lower mass limit: give each range with its source…",
              "tools": [], "tool_args": {}, "no_tool": true,
              "relevant_chunks": ["brown-dwarfs:tr:2"], "must_mention": ["Jüpiter"],
              "must_not_mention": [], "reference_answer": null},
 "source_refs": ["nasa-starchild-bd", "jpl-identity-crisis", "gan-2025-apjl"], "label": "conflicting_sources",
 "verification_status": "unverified", "annotation_status": "ai_drafted_pending_human_review",
 "dataset_version": "qfit_seed_v1", "synthetic": true}
```

Categories:

| | Behaviour |
|---|---|
| A | Data retrieval: right tool and arguments |
| B | Conceptual question answered from the knowledge base |
| C | No data / missing information reported plainly |
| D | Ambiguity or missing target: clarification (or use of frontend context) |
| E | Uncertainty: comparisons, time coverage, conflicting sources |
| F | Citizen science: candidates are not discoveries |
| G | Refusal to fabricate or overclaim |

Honesty fields: `synthetic` (not from a real conversation), `annotation_status`
(`ai_drafted_pending_human_review` → `human_reviewed` → `human_validated`), `verification_status`
(`unverified`, `source_checked`, `expert_verified`). The schema rejects contradictions, for example an
AI-drafted example marked `expert_verified`.

`expected` is written to be checked by code: acceptable first tools, tools that must be called at some
point (`required_tools`), required arguments, relevant
knowledge chunk ids, terms that must or must not appear. `reference_answer` is optional; when present,
every number in it must occur in the input or in its relevant chunks (the same grounding check the
assistant's answers go through), so a reference answer cannot carry an invented value.

## Seed dataset

`research/datasets/qfit_seed_v1.jsonl`: 68 examples in 34 families, every family one Turkish and one
English example, all seven categories. Drafted by an AI assistant, then **reviewed by two team members
on 2026-11-14** (`human_reviewed`; 36 examples also `source_checked` against their sources). They
rewrote every expected behaviour and added 42 reference answers; every source they cited was verified
and added to the registry. The examples remain `synthetic` (written, not taken from real users).

## Pipeline

```powershell
python scripts/build_dataset.py                    # check + split + manifest
python scripts/build_dataset.py --export-vertex    # + Vertex AI SFT files (reviewed examples only)
```

1. **Load and validate** every line against the schema.
2. **Integrity** (`app/training/dataset.py`): unique ids; source ids exist in the registry; chunk ids
   exist in the index; tool names exist; one category per family and at most one example per language;
   reference answers grounded. Errors stop the run; warnings (family without a translation, category
   without examples) are printed.
3. **Split by family**, stratified by category, ordered by a seeded SHA-256 hash: 70 / 15 / 15. A
   translation pair never straddles train and test. `leakage()` re-checks families and identical inputs.
4. **Manifest** `research/datasets/splits/<dataset>/manifest.json`: dataset SHA-256, counts by split,
   category, language, annotation and verification status, leakage report, knowledge index and registry
   versions.
5. **Vertex export** (`app/training/vertex_export.py`, optional): writes `vertex_<split>.jsonl` in the
   Vertex AI Gemini supervised-tuning layout (`systemInstruction`, `contents`, and `tools` for
   function-call targets). By default only `human_reviewed` / `human_validated` examples are exported, so
   the seed set currently exports nothing. Nothing is uploaded; check the layout against current Vertex
   documentation before any upload.

## How examples get better

1. A person reads an example, fixes `expected`, and sets `annotation_status: human_reviewed`.
2. A second person checks it against the cited sources and sets `human_validated` and
   `verification_status: source_checked`.
3. Citizen-science reviews enter a dataset only through `CandidateStore.validated_reviews()` (reviews
   accepted by someone other than their author).
4. Bump `dataset_version`, rebuild the splits, rerun both evaluation suites, commit the reports.
