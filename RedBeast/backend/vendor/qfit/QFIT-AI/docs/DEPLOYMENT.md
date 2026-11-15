# Deploying Q-FIT to the web

Two parts: the Python backend (`QFIT-AI/app/`) and the team's React + Three.js front end (built to
static files; it includes the robin component from `QFIT-AI/mascot/react`). The hosting provider is the team's choice; this page lists what
any choice must provide and a configuration that satisfies it.

## What the host must provide

| Requirement | Why |
|---|---|
| Python 3.12 (or the `Dockerfile`) | The backend |
| **One process, one worker** | Per-client rate limits, the daily AI budget and the candidate log's hash chain live in memory and in one file. Two workers would double the budget and could interleave writes to the log. |
| **A persistent disk** mounted at `QFIT_DATA_DIR` | The candidate log (`<QFIT_DATA_DIR>/citizen/events.jsonl`). Many container platforms wipe the file system on every deploy. |
| **Request timeout ≥ 120 s** at the platform / proxy | A chat answer can take up to `CHAT_TIMEOUT_SECONDS` (90 s) plus the model's last call. Check the platform's documented limit before choosing it. |
| **HTTPS** | Browsers block an `http` API from an `https` page; the API key and team token must not travel in clear text. Most platforms and Caddy provide certificates automatically. |
| Outbound HTTPS to `api.openai.com`, `irsa.ipac.caltech.edu`, `simbad.cds.unistra.fr`, `cds.unistra.fr`, `ssd.jpl.nasa.gov` | The model and the data sources |

Any of these fits: a container platform with a persistent volume and a long enough request timeout, a
small virtual server with Caddy in front, or a university server. Free tiers often fail the
"persistent disk" or "timeout" rows; read their current limits.

## Recommended layout: one domain, no CORS

Serve the built front end and the API from the same domain behind one reverse proxy. The browser then
sees a single origin, so CORS needs no configuration and `VITE_QFIT_API` stays empty.

```
https://qfit.example.org/            -> the front end's build output (static files)
https://qfit.example.org/chat        -> backend :8000
https://qfit.example.org/health      -> backend :8000
https://qfit.example.org/api/...     -> backend :8000
```

Example `Caddyfile` (Caddy obtains the HTTPS certificate itself):

```
qfit.example.org {
    encode gzip
    handle /api/*   { reverse_proxy 127.0.0.1:8000 }
    handle /chat    { reverse_proxy 127.0.0.1:8000 }
    handle /health  { reverse_proxy 127.0.0.1:8000 }
    handle {
        root * /srv/qfit/web          # the front end's build output
        try_files {path} /index.html
        file_server
    }
}
```

If the front end is hosted elsewhere (two domains), build it with
`VITE_QFIT_API=https://api.example.org npm run build` and put the front end's origin in the backend's
`CORS_ORIGINS`.

## Production `.env`

```
LLM_PROVIDER=openai
OPENAI_API_KEY=<secret>
OPENAI_MODEL=gpt-5.4-mini
OPENAI_REASONING_EFFORT=none
HTTP_TIMEOUT_SECONDS=20
HOST=0.0.0.0
PORT=8000
TRUST_PROXY_HEADERS=true            # client IP from the proxy's X-Forwarded-For
CORS_ORIGINS=https://qfit.example.org
CHAT_RATE_LIMIT_PER_MINUTE=10       # per visitor IP
CHAT_DAILY_LIMIT=300                # model calls per UTC day for the whole site; then knowledge-base answers
CHAT_TIMEOUT_SECONDS=90
QFIT_TEAM_TOKEN=<long random string>
QFIT_DATA_DIR=/data
LOG_LEVEL=INFO
```

Generate the team token once and share it only inside the team:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Cost protection, in layers

1. **OpenAI spending limit** in the OpenAI dashboard (a hard monthly cap). The only layer that bounds money
   directly; set it before going public.
2. `CHAT_DAILY_LIMIT`: when reached, `/chat` answers from the knowledge base (`data.fallback.reason_code =
   "rate_limited"`) until midnight UTC. Nothing breaks, nothing is spent.
3. `CHAT_RATE_LIMIT_PER_MINUTE` per visitor IP. Requires `TRUST_PROXY_HEADERS=true` behind a proxy,
   otherwise every visitor shares the proxy's IP and one limit. Leave it `false` when the backend is
   reached directly, or a visitor could fake its IP in a header.
4. `MAX_REQUEST_BODY_BYTES`, the 2000-character message limit and the 20-turn history limit cap the
   size of a single request.

Budget and rate limits are per process and reset on restart; that is acceptable for one small
instance and is why the backend must run as one process.

## Candidate writes

With `QFIT_TEAM_TOKEN` set, `POST /api/v1/candidates...` (create, review, validate, confirm) require the
header `X-QFit-Token`. Reading candidates stays public. `/health` reports
`candidate_writes_protected`. The token proves "a team member", not "which" member: `reviewer_id` is
still self-declared, so the two-person validation rule relies on the team's honesty. A login system
would be needed for named accounts. The chat assistant can still record `ai_generated_candidate`s,
which are the lowest status by design.

## Checks after deploying

```powershell
curl https://qfit.example.org/health
```

- `data.status` is `ok` (not `degraded`), `ai_configured` is `true`, `ai_provider` is `openai`,
  `candidate_writes_protected` is `true`, `knowledge_base.available` is `true`.
- Ask one question in the page and confirm the robin goes thinking → speaking.
- Restart the service and confirm a candidate created before the restart is still listed (persistent
  disk works).
