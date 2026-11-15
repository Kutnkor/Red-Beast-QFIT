# Assistant contract

The assistant is disabled by default. This release implements the interface, validation,
deterministic local mock and source bundle. It contains no model SDK or real provider.
Setting an unsupported provider name or merely setting an API key cannot enable it.

## HTTP

`GET /api/assistant/status` returns `{"enabled":false,"provider":null}` by default.
`BLINKSPACE_ASSISTANT_PROVIDER=mock` enables `{"enabled":true,"provider":"mock"}`.
The client hides the assistant tab when it is disabled. Responses must carry a visible
“AI-generated” label; the mock also explicitly states that no model was called.

`POST /api/assistant/chat` accepts:

```json
{
  "message": "Explain the current view",
  "context": {"ui_language": "en", "mode": "star", "year": 2026},
  "history": [{"role": "user", "content": "A previous question"}],
  "tool_results": []
}
```

The message is at most 4,000 characters. History has at most ten user/assistant messages
of at most 4,000 characters each. Context is at most 4,096 UTF-8 JSON bytes. Private note
and editing-key fields are rejected from context and tool results. Unknown top-level
properties and system-role messages are rejected. At least a message or tool result is
required. A valid request receives `503 assistant_disabled` when the assistant is off.

Enabled responses are `text/event-stream`, never cached. Each event is a separate JSON
payload with an SSE `event:` name and `data:` line:

| Event | JSON payload |
|---|---|
| `text` | `{"delta":"..."}` |
| `command` | `{"tool_use_id":"...","name":"set_year","args":{"year":2100},"requires_confirmation":false}` |
| `sources` | `["motion#model","epistemic#labels","method#6"]` |
| `done` | `{"stop_reason":"end_turn"}` or `tool_use` / `error` |
| `error` | `{"code":"...","message":"..."}` |

The browser validates command arguments against its command registry. The server never
executes these commands. `start_search` and `save_view` require explicit user confirmation.
The client then submits a separate request with the public result:

```json
{"context":{"ui_language":"en"},"tool_results":[{"tool_use_id":"mock_command_1","ok":true,"result":{"year":2100}}]}
```

There are at most ten tool results, each result object at most 4,096 UTF-8 JSON bytes.
Conversation state is supplied by the client, not stored by the server. The current mock
does not validate prior tool IDs against server history because no server history exists;
it acknowledges the client report without claiming to verify a real action.

## Mock scenarios

- Any ordinary message: a fixed model explanation and `set_year` to 2100.
- Exact `mock:save`: proposes `save_view` with confirmation required.
- Exact `mock:search`: proposes a fixed Barnard coordinate search with confirmation required.
- A failed client result: `error` then `done`; a successful one: `text` then `done`.

The mock does not infer intent from arbitrary text, contact a model or measure data.

## Limits and deployment

The shared API RateLimiter allows six requests per minute per client IP. The default global
daily limit is 100 and is configurable with `BLINKSPACE_ASSISTANT_DAILY_LIMIT`; zero or an
invalid value closes the limit. Mock counters remain process-local. QFIT counts each paid provider round in an atomic SQLite
ledger under the runtime data directory; reservations survive restart and reset at UTC day
boundaries. The maximum output is 1,200 tokens by default, up to four rounds and a 60-second turn timeout.
These are request/token bounds, not a currency-spend guarantee.

No message/context/tool-result content is logged. CSP remains same-origin. Deploy with one
worker and configure trusted proxy addresses correctly to preserve per-client IP limits.

## Sources and future provider

`python -m tools.build_knowledge` creates a deterministic bundle of source-hashed chunks
from methods, data sources, features, target reports, the motion model and epistemic labels.
Original report dates remain in the text. Rebuild it after refreshing target reports; an
archived result is not evidence of a new run. The draft system prompt forbids discoveries
and scientific-confirmation claims and requires sources and explicit assumptions.

`MockProvider` retains its original events. The lazy QFIT adapter runs the supplied agent and
Responses transport asynchronously. The existing `done` payload gains optional `qfit` metadata
(message origin, source links, caveats and model); all existing fields/event names stay intact.
Provider response status must be completed; incomplete responses, errors and timeout emit an
error then a clearly non-AI local source card and terminal `done`. Cancelling the browser request
cancels the model operation and closes its HTTP client. Text currently arrives after a complete
provider turn; the mascot's short reveal animation is not represented as token-level API streaming.

Additive routes:

- `GET /api/assistant/commands`: the server mirror of the 12 browser command schemas.
- `POST /api/assistant/knowledge`: the same bounded input, returning a local source card without any model call.
- `GET /api/assistant/sources/{source_id}`: exact lookup in the public versioned sources, never arbitrary filesystem paths.

Set `BLINKSPACE_ASSISTANT_PROVIDER=qfit` and server-only `OPENAI_API_KEY` to configure QFIT.
The supplied provider/model is retained: OpenAI `gpt-5.4-mini`, reasoning `none`. Status exposes
configuration state and model, never a secret. `configured_not_live_verified` means configured,
not a successful paid-provider check. Missing key/vendor leaves AI unavailable; the core app
and local source cards continue. The shipped default remains off.

Only local knowledge and validated command proposals are registered. Generic internet, filesystem,
shell/code and upstream candidate-write services are not mounted. Source passages are data under
BlinkSpace's system rules, with QFIT persona subordinate. The UI never executes raw QFIT actions.
All proposals require a user click; start_search/save_view buttons explicitly say confirmation.
Client results are sent as bounded objects on the next turn. Source links accept only HTTP(S).

The provider uses the [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
with `store:false`, bounded output and raw tool-result replay. The
[function-calling guide](https://developers.openai.com/api/docs/guides/function-calling)
informs the transport boundaries. No browser-side provider connection or API key exists.
