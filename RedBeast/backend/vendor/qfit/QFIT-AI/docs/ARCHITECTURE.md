# Architecture

## Layers

```
app/
├── main.py            App factory: middleware (request id, body limit, logging), CORS, error handlers
├── config.py          Settings from environment / .env
├── api/
│   ├── dependencies.py   Container (wiring), rate limiter, envelope helpers
│   └── routes/           chat · objects · observations · spectrum · health
├── ai/
│   ├── llm_provider.py   Provider-neutral interface (LLMProvider, LLMTurn, ToolCall)
│   ├── openai_client.py  OpenAI implementation (default; Responses API)
│   ├── gemini_client.py  Gemini implementation (kept)
│   ├── ollama_client.py  local-model implementation (kept)
│   ├── prompts.py        System prompt and frontend-context rendering
│   ├── tool_registry.py  Tool definitions: argument models, handlers, presenters
│   └── agent.py          Tool-calling loop and answer assembly
├── services/
│   ├── search_service.py       Catalog lookups, target resolution
│   ├── observation_service.py  Archive search, metadata, observation periods
│   ├── retrieval_service.py    Image and spectral products
│   └── response_builder.py     Service result → object / data / actions / sources
├── astronomy/
│   ├── archive_client.py   IRSA HTTP: SIA2, TAP, retries, cache, URL probe, capped download
│   ├── spherex_client.py   SPHEREx mapping, id lookup, cutouts, pixel sampling
│   ├── object_resolver.py  SIMBAD, Sesame, routing to Horizons
│   ├── horizons_client.py  JPL Horizons API
│   └── data_models.py      CelestialObject, ResolveResult, SpherexProduct, mission constants
├── models/            Request bodies, response envelope
└── utils/             Coordinates and time, validation, errors, logging, TTL cache
```

Dependencies point downwards only: `api → ai → services → astronomy → utils`. The astronomy layer
knows nothing about FastAPI or the model provider.

## Request flows

**Structured endpoint** (`POST /observations/search`):
route → Pydantic validation → `ObservationService` → `SearchService.resolve_target` (only if a name
was given) → `SpherexClient.search_products` → `ArchiveClient.sia_search` → `response_builder` →
envelope.

**Chat** (`POST /chat`):

1. Route checks the rate limit and gets the agent (fails with `ai_unavailable` if no key).
2. `QFitAgent.run` sends system prompt, history, message and frontend context to the provider with
   all tool declarations.
3. If the model returns function calls, `ToolRegistry.execute` validates the arguments with the
   tool's Pydantic model and runs the handler, which calls the same services as the REST routes.
   Failures come back as `{ok: false, error}`; the registry never raises.
4. A compacted copy of each result goes back to the model (long lists cut to eight items, heavy
   fields removed). The full result is kept for the client.
5. The loop ends when the model answers in text, calls `request_clarification`, or reaches
   `AI_MAX_TOOL_STEPS`.
6. Each tool's presenter converts its result into envelope parts; `response_builder.merge` combines
   them (last `focus_map` wins, duplicate actions and sources removed).

So the model writes `message` and nothing else. `object`, `data`, `actions` and `sources` are
computed from archive and catalog responses.

## Reliability rules in code

| Rule | Where |
|---|---|
| Availability comes from the archive response only | `ObservationService`, `RetrievalService` |
| Download URLs are copied or built from archive columns | `product_from_sia`, `product_from_tap` |
| No fixed-position search for moving bodies | `SearchService.resolve_target` |
| Ambiguous names are returned, not guessed | `ObjectResolver.resolve` |
| Spectral image ≠ spectrum | `RetrievalService`, system prompt |
| An archive error document is an error, not an empty result | `parse_csv_table` |
| Download claimed only after a probe | `ArchiveClient.probe_url`, `download_check` |

## Security and robustness

- **Secrets**: `GEMINI_API_KEY` is a `SecretStr`, read from the environment, never logged or returned.
- **Input**: every body and query parameter is a Pydantic model with bounds; unknown fields are
  rejected; object names and observation ids are pattern-checked before they reach ADQL.
- **Errors**: `QFitError` subclasses carry a code and a safe message. Unexpected exceptions are
  logged with the trace and answered with a generic `internal_error`.
- **Limits**: request body size, chat rate limit per client, search radius, archive row cap,
  cutout download size, result paging.
- **Outbound calls**: per-request time-outs, retry with back-off on 429/502/503/504 and transport
  errors (honouring `Retry-After`), TTL cache for archive metadata.
- **CORS**: explicit origin list from `CORS_ORIGINS`.
- **Logging**: JSON lines with a request id on every entry.

## Adding another LLM provider

Implement `LLMProvider.generate(system, messages, tools) -> LLMTurn` in a new module and pass the
instance to `Container(settings, provider=...)`. Messages are plain dicts (`user`, `assistant`,
`tool`), tools are `{name, description, parameters: JSON Schema}`. Agent, tools, services and API
stay unchanged. `LLMTurn.raw` lets a provider keep its native message for the next round, which
Gemini needs for function-call parts.

## Adding a tool

In `tool_registry.py`: define an argument model, write a handler that calls a service, choose or
write a presenter in `response_builder.py`, and register a `Tool`. It then appears in
`/capabilities` and is offered to the model automatically.

## Testing seams

- `Container(settings, transport=httpx.MockTransport(...))` replaces IRSA and Horizons.
- `ObjectResolver._simbad_by_name`, `_simbad_name_candidates`, `_simbad_cone`, `_sesame` are the
  only methods that contact CDS; tests override them.
- `Container(provider=ScriptedProvider(...))` replaces the real model.

## Next phase

Moving-object search along Horizons ephemerides, calibrated spectrum extraction, change detection
between epochs, a shared cache (Redis) and persistent rate limiting, streaming chat responses.
