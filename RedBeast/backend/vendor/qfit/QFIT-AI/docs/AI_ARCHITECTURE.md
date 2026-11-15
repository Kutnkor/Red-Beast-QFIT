# AI architecture

How a `/chat` request becomes an answer, and which parts of that answer can be trusted for what.
The REST data endpoints are described in `ARCHITECTURE.md`; this document covers the AI layer.

## What the model is and is not

- The language model is chosen with `LLM_PROVIDER`: Google Gemini through the Gemini Developer API
  (`app/ai/gemini_client.py`, default), OpenAI through the Chat Completions API with function calling
  (`app/ai/openai_client.py`, plain HTTPS, no SDK), or a local open-weight model served by Ollama
  (`app/ai/ollama_client.py`, `/api/chat` with tool calling). Both sit behind one small interface
  (`app/ai/llm_provider.py`); another provider is one more class.
- **Fallback** (`app/services/fallback.py`, `AI_FALLBACK_ENABLED`): when the model is not configured,
  out of quota, unreachable or failing, `/chat` returns the most relevant knowledge-base passage quoted
  with its source, `intent: knowledge_fallback` (or `assistant_unavailable` when nothing matches),
  `message_source: system` and `data.fallback = {active, reason_code, reason, retryable}`. The
  anti-abuse rate limit (`CHAT_RATE_LIMIT_PER_MINUTE`) never falls back.
- **No model weights are trained in this project.** "Training" Q-FIT means: a curated knowledge base,
  retrieval (RAG), versioned instructions, typed tools and a measured evaluation. See
  `AI_TRAINING_PIPELINE.md` for why, and for the dataset kept for possible future tuning.
- The model never produces data. Every coordinate, date, file, wavelength and measurement in an answer
  comes from a tool result or a knowledge passage; the model only chooses tools and explains results.

## Request flow

```
POST /chat  (or /api/v1/chat)
  │  message, history, context {ra, dec, fov_deg, selected_object, selected_observation_id,
  │                              locale, expertise_level}
  ▼
1. Language        context.locale, else detect_language(message)  → "tr" | "en"
2. RAG prefetch    KnowledgeBase.search(message, language, top_k = RAG_TOP_K)      (v2 only)
3. Prompt          build_system_prompt(version, language, level)
                   render_user_message(message, context, knowledge=hits)  → [K1] [K2] … with sources
4. Tool loop       up to AI_MAX_TOOL_STEPS: model → validated tool call → service → result → model
5. Assembly        each tool result → response_builder presenter → envelope parts, merged
6. Grounding       unsupported_numbers(answer, evidence) → data.grounding + uncertainty
  ▼
QFitResponse  (message_source = "ai_generated")
```

### 1. Language

`app/knowledge/language.py` is a deterministic heuristic (Turkish letters and function words against
English function words). The interface language, `context.locale`, always wins over detection. The
system prompt names the response language; identifiers, units and product names are never translated.

### 2. Retrieval (RAG)

`app/knowledge/` holds the knowledge base:

| Module | Role |
|---|---|
| `registry.py` | Loads `research/sources/registry.json` (31 sources, reliability class, retrieval date). |
| `documents.py` | Parses `research/knowledge/{en,tr}/*.md`. One `##` section = one chunk; every section must end with a `Sources:` line naming registry ids, or ingestion fails. Exact duplicate text is skipped. |
| `index.py` | Builds `research/knowledge/index.json` incrementally (content hashes), validates it, and searches it with BM25. |
| `service.py` | `KnowledgeBase`: finds `research/`, rebuilds the index when documents change, never raises at start-up (a broken knowledge base shows up in `/health`). |

Retrieval is BM25 over folded, stemmed tokens: Turkish diacritics are folded (`cüce` = `cuce`) and Turkish
words are cut to `TR_PREFIX_LENGTH` letters; English gets light suffix stemming. Passages scoring below
3.0 are dropped. If nothing in the user's language passes, the other language is tried and
`other_language_used` is set. A vector database is not used: the corpus is 82 chunks, and the
evaluation (`MODEL_EVALUATION.md`) measures whether lexical retrieval is good enough. Embeddings are an
optional, untested second signal (`GEMINI_EMBEDDING_MODEL`, not wired to Gemini yet).

### 3. Instructions

`app/ai/prompts.py` keeps versioned instruction sets; `QFIT_INSTRUCTION_VERSION` selects one.

| Version | Content |
|---|---|
| `v1` | The original retrieval-only rules, English only, no knowledge excerpts. Kept as the evaluation baseline and for rollback. |
| `v2` (default) | Role; evidence rules (tool result / knowledge excerpt / general knowledge, each number from evidence); uncertainty policy (evidence classes, no confidence percentages, conflicting sources shown side by side, no brightness comparison across wavelengths or releases, gaps are "not observed"); candidate rules (never "discovery"); tool rules; language and user level. |

Scientific facts are deliberately not in the instructions: they live in the knowledge base, where each
has a source.

### 4. Tools

Eleven tools in `app/ai/tool_registry.py`. Arguments are pydantic models (validated before anything
runs); failures come back to the model as `{"ok": false, "error": …}`, never as exceptions.

| Tool | Data source |
|---|---|
| `search_celestial_object`, `resolve_object_coordinates`, `search_objects_by_coordinates` | SIMBAD / Sesame / JPL Horizons |
| `search_spherex_observations`, `get_spherex_observation_metadata`, `retrieve_spherex_image`, `retrieve_spherex_spectral_data`, `get_available_observation_periods` | NASA/IPAC IRSA |
| `search_knowledge_base` | Q-FIT knowledge base |
| `submit_candidate_for_review` | Candidate log (records an `ai_generated_candidate`; only when the user asks) |
| `request_clarification` | Ends the turn with a question |

### 5. Assembly: the envelope fields

| Field | Built from | Trust |
|---|---|---|
| `message` | Model text | Explanation. Check `data.grounding` and `uncertainty`. |
| `object`, `data`, `actions`, `media` | Tool results via `response_builder.py` | Retrieved data. |
| `sources` | Service sources + knowledge passage sources | Provenance. |
| `evidence` | One entry per tool result / knowledge passage, with a class: `catalog_data`, `archive_metadata`, `direct_measurement`, `knowledge_base`, `candidate_record`, `missing_information` | What the answer rests on. |
| `uncertainty` | Tool caveats, archive limits, verification notes on passages, tool failures, grounding warnings | Read it. |
| `language` | Step 1 | |
| `meta.versions` | Instruction version, knowledge index version, source registry version, `data.json` version | Reproducibility. |

### 6. Grounding check

`app/ai/grounding.py` extracts every number and date from the model's text and looks for the same value,
at the precision written, in the evidence the model saw (user message, context, history, tool results,
knowledge passages). Dates, identifiers (`spherex_qr3:…`, `M31`), catalog names (`M 31`, `NGC 224`),
list markers and small integers (≤ 10) are skipped. Turkish decimal commas and thousands separators are
understood. Unmatched numbers go to `data.grounding.unsupported_numbers` and to `uncertainty`. The check
flags; it does not rewrite the answer.

## Scientific configuration (`research/data.json`)

`app/scientific/config_loader.py` finds, loads, versions and structurally checks the team's
`data.json` without assuming its schema, and reports problems instead of fixing them. The file is not in
this repository yet, so phase descriptions and threshold evaluation are not implemented: no threshold or
schema has been guessed. `/health` shows `scientific_config.status` (`missing`, `invalid`, `loaded`).

## Citizen-science candidates

`app/citizen/store.py` is an append-only, hash-chained JSONL log
(`<QFIT_DATA_DIR>/citizen/events.jsonl`). States: `ai_generated_candidate` → `unreviewed_candidate` →
`human_reviewed_candidate` → `scientifically_confirmed` (only with a recorded external reference).
A review can be validated only by someone other than its author; only validated reviews may enter a
dataset. Editing the log breaks the chain, which `/health` and `/candidates/{id}/audit` report.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini`, `openai` or `ollama` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | empty / empty / `https://api.openai.com/v1` | OpenAI key (server only), model, endpoint |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | `http://127.0.0.1:11434` / empty | Local model server and model name |
| `AI_FALLBACK_ENABLED` | `true` | Answer `/chat` from the knowledge base when the model fails |
| `QFIT_INSTRUCTION_VERSION` | `v2` | Instruction set |
| `RAG_ENABLED` | `true` | Prefetch knowledge passages (ignored for `v1`) |
| `RAG_TOP_K` | `4` | Passages per question |
| `GEMINI_EMBEDDING_MODEL` | empty | Reserved; lexical retrieval only |
| `QFIT_DATA_DIR` | `data` | Runtime data (candidate log), relative to the backend root |
| `QFIT_RESEARCH_DIR` | auto | Override where `research/` is found |
| `QFIT_SCIENTIFIC_CONFIG` | auto | Override the path of `data.json` |
