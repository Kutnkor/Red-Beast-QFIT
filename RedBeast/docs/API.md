# RedBeast Python API

The FastAPI server serves the React/V4 application and the scientific API from the same
origin. The `blinkspace` Python package name and `/api/` routes are retained for compatibility
with earlier BlinkSpace clients. The assistant is still QFIT.

## Run and inspect

From the application directory, run `./Start-BlinkSpace.command` on macOS, or
`docker compose up --build` for the container. The launcher uses port 8765; Compose uses 8000.

- Health: `http://127.0.0.1:8765/api/health`
- Interactive API reference: `http://127.0.0.1:8765/api/docs`
- Live OpenAPI schema: `http://127.0.0.1:8765/api/openapi.json`
- Versioned schema snapshot: [openapi.json](openapi.json)

Python 3.12+ is required. Exact runtime dependencies are in `backend/requirements.lock`.
The ready release includes five public targets and 25 actual SPHEREx cutouts. New coordinate
queries require access to the upstream archive. The server uses one worker and a writable
SQLite/data directory; a static GitHub Pages deployment cannot run this API.

## QFIT configuration

Copy `.env.example` to `.env` in the application directory, then set:

```dotenv
BLINKSPACE_ASSISTANT_PROVIDER=qfit
OPENAI_API_KEY=YOUR_SERVER_SIDE_KEY
BLINKSPACE_ASSISTANT_DAILY_LIMIT=100
QFIT_MAX_OUTPUT_TOKENS=1200
QFIT_TIMEOUT_SECONDS=60
```

Restart the server. `GET /api/assistant/status` reports whether the provider is configured;
it never returns the key. The macOS launcher reads `.env`; Compose passes the configured
assistant variables to the container. For a hosting provider, set these values in its
server secret/environment settings. The repository and browser bundle contain no personal
API keys. `off` supports local source cards; `mock` is available for contract tests.

The optional AI provider uses the supplied QFIT configuration. Responses include sources
and proposed interface actions; changes still go through the application's action contract.
See [ASSISTANT_CONTRACT.md](ASSISTANT_CONTRACT.md) and [AI_USAGE.md](AI_USAGE.md).

## Observation workflow

```bash
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:8765/api/targets
curl -X POST http://127.0.0.1:8765/api/searches \
  -H 'Content-Type: application/json' \
  -d '{"target_id":"barnard","max_frames":6}'
```

Use the returned job ID with `/api/jobs/{job_id}` until processing completes, then load
the resulting `/api/sequences/{seq_id}`. Ready sequences are also advertised by `/api/targets`.
`POST /api/jobs/{job_id}/cancel` cancels a running job. Invalid coordinates and unsupported
parameters return validation errors instead of fabricated observations.

For a custom position, supply `ra`, `dec`, `ra_unit`, `fov_arcmin`, `max_frames` and optional
wavelength/date constraints. A wavelength mismatch or low-quality alignment remains visible
in the sequence metadata. Do not interpret unequal wavelengths as a brightness change.

Saved user observations use an editing key for updates and deletion. That key belongs to
the client who created the observation; it is not the OpenAI key. The distributed seed is
sanitized and excludes user notes, editing keys, searches and jobs.

## Endpoint inventory

Request and response fields, ranges, headers and error responses are specified by the
OpenAPI schema. File endpoints may return binary arrays/images rather than JSON.

| Area | Routes |
| --- | --- |
| Status | `GET /api/health` |
| Targets and 3D inputs | `GET /api/targets`, `/api/motion`, `/api/models`, `/api/sky/bright.bin`, `/api/sky/bright.json` |
| Archive jobs | `POST /api/searches`, `GET /api/jobs/{job_id}`, `POST /api/jobs/{job_id}/cancel` |
| Spectra | `POST /api/spectra`, `GET /api/spectra/{result_id}` |
| Sequence and files | `GET /api/sequences/{seq_id}`, `/files/{name}`, `/provenance` |
| Image comparison | Sequence suffixes `/diff`, `/stack`, `/track`, `/track_stack` |
| Analysis | Sequence suffixes `/lightcurve`, `/overlay`, `/candidates` |
| Saved observations | `POST /api/observations`; `GET`, `PUT`, `DELETE /api/observations/{obs_id}` |
| Tutorials | `GET /api/tutorials` |
| QFIT | `GET /api/assistant/status`, `/commands`, `/knowledge`, `/sources/{source_id}`; `POST /api/assistant/chat` |

## Operational checks

`BLINKSPACE_ARCHIVE_PROTOCOL=sia` selects the official IRSA SIA service. In `auto` mode,
the official TAP probe is limited to 20 seconds before SIA fallback. Actual cutout downloads
have separate timeouts and can still fail if upstream files are unavailable. Existing ready
sequences remain usable. See [DEPLOY.md](DEPLOY.md) for persistent storage, proxy settings,
container initialization and data refresh; [UI_AUDIT.md](UI_AUDIT.md) records this revision's
verification and remaining external-service limits.
