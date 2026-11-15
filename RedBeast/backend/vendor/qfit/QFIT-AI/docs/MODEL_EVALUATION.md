# Model evaluation

Two suites, both driven by the example dataset (`AI_TRAINING_PIPELINE.md`). Reports (JSON with every
row, plus a Markdown summary) go to `research/evaluation/reports/`.

```powershell
python scripts/evaluate.py retrieval                       # no key, no network, seconds
python scripts/evaluate.py agent                           # GEMINI_API_KEY + network, uses API quota
python scripts/evaluate.py agent --split test --limit 10   # a smaller, cheaper run
```

## Retrieval suite (`app/evaluation/retrieval.py`)

Every example with `expected.relevant_chunks` is a query (42 in the seed set: 21 per language).
Relevance is strict: a chunk counts only if its exact id (document, language, section) is listed.

| Metric | Meaning |
|---|---|
| precision@k | share of the top k that is relevant; with 1-2 relevant chunks and k = 4 it cannot exceed 0.5 |
| recall@k | share of the relevant chunks found in the top k |
| MRR | mean of 1 / rank of the first relevant chunk (0 if none) |
| empty rate | share of queries where nothing passed the score threshold |

Configurations: `naive` (raw term overlap, no stemming, no language handling: the baseline) and BM25
with Turkish words cut to 4, 5 or 6 letters.

### Result, 2026-11-14 (seed set v1, 42 queries)

After adding the heading-match bonus (`Retriever.HEADING_BONUS`, see below):

| configuration | P@4 | R@4 | MRR | empty | MRR tr | MRR en |
|---|---|---|---|---|---|---|
| naive | 0.214 | 0.774 | 0.625 | 0.000 | 0.627 | 0.623 |
| bm25, prefix 4 | 0.250 | 0.881 | 0.817 | 0.000 | 0.813 | 0.821 |
| bm25, prefix 5 (in use) | 0.244 | 0.869 | 0.817 | 0.000 | 0.813 | 0.821 |
| bm25, prefix 6 | 0.238 | 0.845 | 0.812 | 0.000 | 0.802 | 0.821 |

Before the bonus, BM25 prefix 5 scored MRR 0.770, recall 0.845, empty rate 0.048.

Reading it:
- BM25 with language handling beats the baseline clearly: MRR 0.625 → 0.817.
- **Heading match.** "What is SPHEREx?" / "SPHEREx nedir?" reduce to one token that occurs in most
  chunks, so BM25 stayed under the 3.0 threshold and nothing was returned. A section whose heading
  tokens are all contained in the query now gets +3.0. This fixed both queries and changed no other
  ranking for the worse.
- Prefix 4 and 5 now tie on MRR; 4 finds one more relevant chunk in the top 4. Not enough evidence on
  an unreviewed set to change `TR_PREFIX_LENGTH` (still 5).
- Remaining misses: "Did I discover a new brown dwarf?" and "how sure are you, as a percentage". The
  questions share their words with the brown-dwarf passages, not with the policy passages that answer
  them. These behaviours are enforced by the instructions, so retrieval is not the only safeguard.

## Agent suite (`app/evaluation/agent_eval.py`)

Runs the real agent (Gemini + live data tools) on every example and scores only the checks that
example defines:

| Check | Passes when |
|---|---|
| tool_selection | the first tool is one of `expected.tools` |
| tool_arguments | that call contains `expected.tool_args` (numbers within 1e-3) |
| no_data_tool | for `no_tool` examples, no tool except `search_knowledge_base` was called |
| language | the answer is in the example's language (same heuristic detector as the backend) |
| must_mention / must_not_mention | listed terms present / absent (case and Turkish letters folded) |
| source_grounding | a relevant chunk reached the model (prefetch or tool call) |

Run-level: share of answers with unsupported numbers (grounding check), mean unsupported numbers per
answer, latency mean and p95, error rate. Default comparison: `v1_no_rag` (old instructions, no
retrieval) against `v2_rag` (current). Errors are recorded per row; one failure does not stop a run.

### Results, 2026-11-14 (OpenAI `gpt-6-astra`, 10 examples covering all seven categories)

The Gemini free tier (20 requests/day) could not run the suite; the team then moved to OpenAI.

| check | v1, no RAG (first run) | v2 + RAG, after fixes |
|---|---|---|
| tool_selection | 3/3 | 3/3 |
| tool_arguments | 1/1 | 1/1 |
| no_data_tool | 4/7 | 5/5 |
| language | 7/9 | 10/10 |
| must_mention | 3/5 | 6/7 |
| source_grounding | 1/7 | 7/7 |
| answers with unsupported numbers | 0 | 0 |
| errors | 0 | 0 |
| latency mean / p95 | 108 s / 397 s | 27 s / 90 s |

The first v2 run lost 4 of 10 examples to a dropped network connection; the right column is a clean
rerun after these fixes:
- the cutout download now honours IRSA's 503 + Retry-After, has its own 90 s timeout, runs at most
  2 downloads at once, and the chat tool samples 3 exposures by default instead of 6 (the v1 answers
  that read pixel values took 6-7 minutes);
- a heading-match bonus in retrieval (see above);
- an instruction to answer the general part of a question before asking for a missing detail (v2 had
  answered "did the star change?" with only a clarifying question);
- two dataset expectations that marked correct answers as wrong (a valid alternative tool; `MJy`
  folded to `mjy` matched a forbidden `mJy`).

v1 answered Turkish questions in English and used knowledge passages rarely: v1 has no language rule
and no retrieval, which is what v2 was written to fix. The one remaining v2 miss: "What is SPHEREx?"
was answered correctly from the knowledge base but without the word "infrared", which the example
expects as the mission's key fact. Ten examples are a smoke test, not a benchmark.

### Full run, 2026-11-14 (OpenAI `gpt-6-astra`, v2 + RAG, all 68 human-reviewed examples)

| check | result |
|---|---|
| tool_selection | 24/26 |
| tool_arguments | 10/10 |
| no_data_tool | 39/42 |
| language | 66/66 |
| must_mention | 39/42 |
| must_not_mention | 5/6 |
| source_grounding | 38/42 |
| answers with unsupported numbers | 1/68 (a checker false positive, fixed) |
| errors | 0 |
| latency mean / p95 | 13.7 s / 44.7 s |

Every failed check was read by hand:

| Example | What happened | Action |
|---|---|---|
| a-periods-m31-tr | "21" flagged as unsupported: the model wrote times as `2025-08-14 21:33:28` (space, not `T`); the grounding check only recognised ISO `T` times | **Fixed** in `grounding.py`, test added |
| b-what-is-spherex-tr | Correct answer without "infrared": the overview passage never said SPHEREx observes in the infrared | **Fixed**: one sourced sentence added to the overview passage (en/tr); verified live |
| b-y-dwarfs-en/tr | Correct answers (coolest class, 200-500 K) without "WISE" | **Decided**: WISE is optional; requirement removed |
| c-temperature-missing-en/tr, g-invent-flux-en | The model looked up the archive first, then correctly said no temperature / no flux is available; the examples expect no data tool | **Decided**: a lookup first is acceptable; no value may be invented |
| f-did-i-discover-en | "not evidence that you discovered" matched the forbidden term "you discovered" (checker cannot see negation) | **Decided**: forbidden terms are now "congratulations" / "tebrikler" |
| f-submit-candidate-en/tr | Searched observations first, then recorded the candidate with those ids (arguably better); the check requires submit first | **Decided**: a search first is allowed; new `required_tools` check makes the submission mandatory |
| f-did-i-discover, g-confidence-percent (source_grounding) | Retrieval returns brown-dwarf passages, not the policy passages; answers were still correct | Known retrieval limit; a "-ery" stemming rule was tried and changed nothing, so it was not kept |

After the four team decisions the 10 affected examples were rerun live (2026-11-14): every check
passed except source_grounding for f-did-i-discover-en/tr (the known retrieval limit; both answers
were correct). No errors, no unsupported numbers, mean latency 12.2 s.

The scoring code is unit-tested with a scripted model (`tests/test_evaluation.py`), so a live run
measures Gemini, not the harness.

## Limits of these numbers

- The seed set is AI-drafted and unreviewed. Treat results as regression signals, not as a benchmark.
- Keyword checks are coarse: an answer can mention "candidate" and still be wrong. Read the rows.
- The language detector is heuristic; very short or mixed answers can be misjudged.
- Live data tools make the agent suite depend on IRSA / SIMBAD / Horizons availability on the day.
- Nothing here measures scientific correctness of explanations beyond the grounding check; that needs
  human review.
