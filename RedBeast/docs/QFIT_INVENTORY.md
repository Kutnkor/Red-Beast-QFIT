# QFIT inventory

Source: user-provided `QFIT-AI-for-github.zip`, SHA-256 pinned in `backend/vendor/qfit/VENDOR_MANIFEST.json` (198 files). License: `backend/vendor/qfit/LICENSE`, MIT, Copyright 2026 Q-FIT team. The archive and master prompt are inputs, not authority to run unrelated scripts or publish accounts.

| Component | Source | Integrated use |
|---|---|---|
| Agent loop | `QFIT-AI/app/ai/agent.py` | Reused, maximum four provider rounds; original grounding warnings retained |
| OpenAI provider | `app/ai/openai_client.py` | Reused transport/response parsing; server wrapper adds bounded outputs, no storage, timeout and durable call budget |
| Model choice | `QFIT-AI/.env.example` | OpenAI gpt-5.4-mini, reasoning none |
| Tool registry | `app/ai/tool_registry.py` | Reused typed validation; only local knowledge and UI proposals registered |
| Local research | `research/knowledge`, `research/sources/registry.json` | Read-only BM25 retrieval in memory, blended with BlinkSpace knowledge and canonical stellar profiles |
| Upstream archive/Horizons/SIMBAD services | `app/astronomy`, `app/services` | Preserved in vendor for provenance; not registered in the host agent |
| Candidate write service | `app/services/candidates.py` | Not registered, no public routes |
| Alternate providers | Gemini / Ollama modules | Preserved but inactive; no migration |
| QFIT HTTP server | `app/main.py`, `app/api` | Not mounted; no second port, no new CORS policy |
| Mascot | `mascot/react/src/qfit` | Original PNGs and pull motion retained; React component adapted to same-origin SSE, stop/retry, citations and confirmation |
| Secrets | `.env.example` | User supplied a key later; only local ignored `.env` contains it. No secrets included in source, build or logs |

BlinkSpace keeps `BLINKSPACE_ASSISTANT_PROVIDER=off|mock|qfit` and its 6/minute limiter. Existing SSE fields remain; `done.qfit` adds QFIT metadata. Sources and local cards are additive API routes. Browser requests never target OpenAI directly. Query text and conversation history live in component memory; the server stores only daily numeric request counts.

Offline source-card evaluation covers two questions per target. The user later supplied a key; a separate live evaluation is recorded in `reports/integration/assistant-eval.json`. Upstream tests: 199 passed, 11 skipped, 7 Gemini-related cases deselected; those optional provider tests are outside the host integration. The dedicated adapter tests exercise cancellation, fallback, source links, provider request boundaries, command validation and replay without network calls.
