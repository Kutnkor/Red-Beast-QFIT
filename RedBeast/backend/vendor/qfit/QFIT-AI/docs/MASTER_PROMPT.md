<!--
KULLANIM (Türkçe): Bu dosyanın tamamını, projeyi birleştirecek yapay zekâya verdiğiniz son
birleştirme prompt'una EK olarak yapıştırın. Q-FIT AI'nin ne olduğunu, nasıl çalıştığını, teknik
sözleşmesini, kızılgerdan maskotunun animasyonlarını ve birleştirmede uyulması gereken kuralları
anlatır. Bilgiler 2026-11-14 itibarıyla koddan doğrulanmıştır. Ayrıntı gerektiğinde yapay zekâ
QFIT-AI/docs/ altındaki belgelere bakmalıdır.
-->

# MASTER PROMPT — Q-FIT AI (attach to the final merge prompt)

You are merging the Q-FIT project into one application. This document describes the **Q-FIT AI**
part, which lives in the repository folder `QFIT-AI/`. Other team members built the React + Three.js
3D scene and the user interface in other folders. Your job is to connect the two **without changing
how the AI works**. Read this whole document before editing anything. Everything below was checked
against the code on 2026-11-14; where a detail is missing here, the files under `QFIT-AI/docs/` are
the authority.

---

## 1. What Q-FIT AI is

- **Project:** NASA Space Apps Challenge, SPHEREx. SPHEREx is a NASA space telescope that maps the
  whole sky in near-infrared light (0.75–5.0 µm, 102 spectral channels, six detector bands, the whole
  sky about every six months). Its data are served by NASA/IPAC IRSA.
- **Q-FIT AI** is the project's research assistant: a Python backend with an AI agent, a cited
  knowledge base, real archive tools, and a mascot (a robin, "kızılgerdan") with a chat panel.
- **What it does:** understands Turkish and English requests ("Beni Vega'ya götür", "What SPHEREx data
  is there for M31?"), moves the 3D view to sky positions, fetches real SPHEREx observations, image
  previews, observation periods and spectral information from the archive, answers conceptual
  questions from a cited knowledge base, and records citizen-science candidates for human review.
- **Name:** "Quantum Framework for Intelligent Tracking". "Quantum" is only a name; no quantum computing.

### Non-negotiable rules (do not weaken them while merging)
1. **No fabricated data.** Every coordinate, date, wavelength, brightness, count, identifier and URL
   comes from a tool result or a cited knowledge passage. The model never invents numbers. A
   grounding check flags any number in the AI's text that is not in its evidence.
2. **A catalog match is not an observation.** Only `data.spherex_available == true` means SPHEREx
   data exist for a position.
3. **A candidate is not a discovery.** Statuses: `ai_generated_candidate`, `unreviewed_candidate`,
   `human_reviewed_candidate`, `scientifically_confirmed` (only with an external reference).
4. **No data means no data**, stated plainly. Gaps in time coverage mean "not observed", never "no change".
5. **No confidence percentages** invented by the model.
6. **Image previews are display images, not measurements** (one band, one exposure, stretched).
7. **The API key never reaches the browser.** It lives only in the backend's `.env`.

---

## 2. Repository layout

```
<repo root>/
  .github/workflows/qfit-ai.yml   CI: backend unit tests + type check of the React mascot (runs when QFIT-AI/ changes)
  LICENSE                         MIT (whole repository)
  QFIT-AI/
    app/                          FastAPI backend: api/, ai/, astronomy/, services/, knowledge/, citizen/, training/, evaluation/
    research/                     knowledge base (TR/EN markdown), source registry, datasets, evaluation reports
    scripts/                      build_dataset.py, evaluate.py, build_mascot_assets.py, live_check.py
    tests/                        unit tests (no network) + live tests (--run-live)
    docs/                         API_CONTRACT, FRONTEND_CONTRACT, MASCOT_AND_CHAT_UI, DEPLOYMENT, AI_ARCHITECTURE, ...
    mascot/
      assets/                     robin art: source/ (originals), normalized/, spritesheets/, icons/, mascot.json
      react/src/qfit/             THE COMPONENT TO COPY: QFitAssistant.tsx, qfit-assistant.css, api.ts, assets/
      vanilla/                    same mascot + panel as plain HTML/CSS/JS (qfit-widget.css, qfit-widget.js)
    requirements.txt  run.py  Dockerfile  .env.example  README.md  HANDOFF.md (Turkish work log)
```

Do not move files inside `QFIT-AI/` unless necessary: the backend finds `research/` relative to its
own location, and the mascot CSS finds its images relative to the CSS file.

---

## 3. Running it

```bash
cd QFIT-AI
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                   # fill in OPENAI_API_KEY
python run.py                                          # http://127.0.0.1:8000, Swagger UI at /docs
pytest                                                 # unit tests: 201 pass, no network, no key
pytest --run-live -rs                                  # live tests; external outages are reported as BLOCKED
```

The backend runs as **one process / one worker on purpose** (rate limits, the daily AI budget and the
candidate log's hash chain live in that process). Never start it with several workers.

### Key settings (`.env`)
| Variable | Value used by the team | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` (used), `gemini`, `ollama` (kept as alternatives) |
| `OPENAI_API_KEY` | secret | server only |
| `OPENAI_MODEL` | `gpt-5.4-mini` | chosen for speed; measured below |
| `OPENAI_REASONING_EFFORT` | `none` | no reasoning step: fastest |
| `AI_FALLBACK_ENABLED` | `true` | if the model fails, answer from the knowledge base instead of an error |
| `CHAT_TIMEOUT_SECONDS` | `90` | a whole chat turn; past it, knowledge-base fallback |
| `HTTP_TIMEOUT_SECONDS` | `20` | archive calls (healthy IRSA answers in 2–3 s) |
| `CHAT_RATE_LIMIT_PER_MINUTE` | `20` (10 in production) | per visitor IP |
| `CHAT_DAILY_LIMIT` | `500` | model calls per UTC day for the whole site, then fallback |
| `TRUST_PROXY_HEADERS` | `false` locally, `true` behind a proxy | client IP from X-Forwarded-For |
| `QFIT_TEAM_TOKEN` | secret in production | candidate writes need header `X-QFit-Token` |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | add the deployed front-end origin |
| `QFIT_DATA_DIR` | `data` (a persistent disk in production) | candidate log location |

---

## 4. How the AI works (one chat turn)

`POST /chat` (alias of `/api/v1/chat`) with
`{ "message": "...", "history": [{role, content}...≤20], "context": {ra, dec, fov_deg, selected_object, selected_observation_id, locale, expertise_level} }`:

1. **Limits:** per-IP rate limit, then the site's daily budget (if used up → knowledge-base answer).
2. **Language:** `context.locale` (`tr`/`en`) wins; otherwise a deterministic detector (Turkish letters,
   words, and apostrophe suffixes like "Vega'ya"). The answer is written in that language.
3. **RAG prefetch:** BM25 search over the knowledge base (82 passages, 41 per language, every passage
   cites registry sources; 40 sources in `research/sources/registry.json`). Up to 4 passages go to the
   model as `[K1]…[K4]` excerpts with their sources. Turkish words are cut to 5 letters, diacritics folded;
   a section whose heading matches the question gets a bonus. Retrieval quality on the reviewed dataset: MRR 0.815, recall@4 0.869 (a naive baseline: 0.673).
4. **Instructions:** versioned set `v2` (`app/ai/prompts.py`): evidence rules, uncertainty policy,
   candidate rules, tool rules, navigation rule, brevity (at most 3 short sentences; the UI shows details).
5. **Tool loop** (OpenAI **Responses API** with function calling, at most 6 steps): the model calls
   tools; tool calls of one turn run **in parallel**; placeholder arguments the model sends
   (`ra: 0, dec: 0` next to an object name, empty strings) are removed before validation.
6. **Assembly:** each tool result becomes envelope parts (`object`, `data`, `actions`, `sources`,
   `evidence`, `uncertainty`, `media`) built **from data, never from model text**.
7. **Grounding check:** numbers in the model's text not found in its evidence go to
   `data.grounding.unsupported_numbers` and to `uncertainty`.
8. **Timing** per step in `data.timing` (`model_calls`, `model_ms`, `tools_ms`).
9. **Failure handling:** no key, quota, model error, slow archive or the 90 s deadline → a cited
   knowledge-base passage with `data.fallback.active = true`, `message_source = "system"`. The UI never
   breaks because of the AI.

### The 11 tools
| Tool | Source |
|---|---|
| `search_celestial_object`, `resolve_object_coordinates`, `search_objects_by_coordinates` | SIMBAD (circuit breaker: after a failure skipped for 5 min), CDS Sesame fallback, JPL Horizons for Solar System bodies |
| `search_spherex_observations`, `get_spherex_observation_metadata`, `retrieve_spherex_image`, `retrieve_spherex_spectral_data`, `get_available_observation_periods` | NASA/IPAC IRSA (SIA2, TAP, cutout service) |
| `search_knowledge_base` | Q-FIT knowledge base |
| `submit_candidate_for_review` | candidate log (only when the user asks) |
| `request_clarification` | asks the user (only when no useful answer is possible without it) |

**Navigation behaviour:** "take me to X / go to X / show me X / beni X'e götür / X'e git / X'i göster"
→ only `resolve_object_coordinates`; the answer is 1–2 sentences ("İşte Vega." + one basic fact, no
coordinates, offer to look up SPHEREx data). The `focus_map` action moves the camera.

### Measured performance (gpt-5.4-mini, effort none, 12 questions, 2026-11-14)
Mean **8.4 s**; conceptual questions 2.3 s; navigation 4.2 s; archive questions 25 s (IRSA had an
outage that day; healthy archive queries take 2–3 s). Quality: correct language 12/12, grounded 7/7,
no invented numbers, no errors. A full 68-example evaluation (earlier model) and the method are in
`docs/MODEL_EVALUATION.md`.

---

## 5. The API contract (what the front end receives)

Every endpoint, success or failure, returns the same envelope:

```json
{ "success": true, "assistant": "Q-FIT", "intent": "...", "message": "...",
  "message_source": "ai_generated | system", "object": {...} | null,
  "data": { "spherex_available": true|false|null, "observations": [], "spectral_products": [],
            "image_products": [], "...": "..." },
  "actions": [ { "type": "...", "payload": {...} } ], "sources": [ {name, url} ],
  "language": "tr|en|null", "evidence": [], "uncertainty": [], "media": [],
  "error": null | { "code", "message", "retryable", "details" },
  "meta": { "request_id", "timestamp", "api_version", "tools_called", "ai_model", "versions" } }
```

**Actions to execute in order:** `focus_map` (turn camera to `payload.ra/dec`; `epoch_utc` present =
moving Solar System body), `display_object`, `display_observations`, `display_image` (products with
`preview_url`), `display_spectrum`, `request_clarification` (show `question` + `options` as buttons),
`show_error`.

**Endpoints** (prefix `/api/v1`; `/health` and `/chat` also at the root):
`GET /health`, `GET /capabilities`, `POST /chat`, `POST /objects/search`, `POST /objects/by-coordinates`,
`GET /objects/{name}`, `POST /coordinates/resolve`, `GET /observations`, `POST /observations/search`,
`POST /observations/periods`, `GET /observations/{id}`, `POST /images/search`,
`GET /images/preview` (PNG), `GET /images/preview/info`, `POST /spectrum/search`, `GET /spectrum/{id}`,
`POST /knowledge/search`, `GET /knowledge/sources`, `POST|GET /candidates`, `GET /candidates/{id}`,
`POST /candidates/{id}/reviews`, `POST /candidates/{id}/reviews/{review_id}/validation`,
`POST /candidates/{id}/confirmation`, `GET /candidates/{id}/audit`. Full detail: `docs/API_CONTRACT.md`.

### Image previews (FITS → PNG for Three.js)
SPHEREx files are FITS, which browsers cannot show. `GET /api/v1/images/preview?observation_id=…&ra=…&dec=…&size_deg=0.5&stretch=asinh`
returns a grey+alpha PNG (blank pixels transparent; asinh/log/linear stretch; clipped at the 1st and 99.5th
percentile). `/images/preview/info` returns `png_url`, size, stretch range in MJy/sr and
**`corners_radec`** (ICRS position of the PNG's top-left, top-right, bottom-right, bottom-left
corners). SPHEREx images are **not north-up** (the M31 example is rotated about 20°), so place the
texture by its four corners. First request 10–45 s (IRSA cutout), then cached for an hour. Verified
with a real SPHEREx image of M31.

---

## 6. The robin mascot and its animations

### Assets (`QFIT-AI/mascot/assets/`, described by `mascot.json`)
- `source/robin_figure.png` — the **official figure**: robin with a light beam from its eye to a star.
- `source/robin_thinking.gif` — thinking: a thought bubble with "…" (9 frames × 350 ms).
- `source/robin_speaking.gif` — speaking: beak opens, sparkles (9 frames × 80 ms).
- `normalized/` — every state on **one shared canvas, 320 × 272 px**, bird 192 px tall, body centre
  x = 120, feet on y = 250. Switching states is a pure image swap; nothing jumps.
  `idle.png` (figure), `quiet.png` (bird without beam), `thinking/frame_00..08.png`, `speaking/frame_00..08.png`.
- `spritesheets/thinking.png`, `spritesheets/speaking.png` — 9 frames side by side (2880 × 272).
- `icons/robin_{512,256,128,64,32}.png`.
- Originals are never modified; `scripts/build_mascot_assets.py` rebuilds everything (and the copies
  in `mascot/react/src/qfit/assets/`). Thinking frame 6 had a smudge from the fading bubble; the
  normalized frame is cleaned.

### States (CSS animations on top of the art; the art is never redrawn)
| State | Look | When |
|---|---|---|
| `idle` | official figure; breathing (3.6 s), eye glow pulse (2.4 s), star twinkle (3.1 s) | default |
| `thinking` | thinking frames, looping | from sending a question until the answer arrives |
| `speaking` | speaking frames, looping | while the answer is typed out (at most 4 s) |
| `found` | star flare once (1.2 s) → idle | real archive data came back (`spherex_available == true` or `media`) |
| `quiet` | bird without beam, calm head tilt (−5° → −2°), held 2.5 s → idle | failure, fallback, no data, tool errors |
| attention | two hops + orange badge | an answer arrived while the panel was closed |
| hover | lifts 4 px | pointer over the robin |

Glow/star overlay points on the canvas: eye (110.6, 83.5), star (222.3, 47.8).
`prefers-reduced-motion` turns every animation off.

### The beak-pull animation (opening the chat)
- Closed: only a small orange **handle** of the panel shows at the screen edge, level with the beak.
- Click the robin (or the handle): **grab** (180 ms) — the robin turns to the panel, closes its beak
  (`quiet` art), reaches to the handle; **pull** (600 ms) — it walks backwards, leaning back, and the
  panel slides out following the beak; open — it stands at the panel edge, beak on the handle.
  Closing plays it in reverse (it pushes the panel back, steps into its corner, turns to the screen).
- Alignment: the beak tip of `quiet.png` is at (169, 85) on the canvas; the robin's position and the
  panel slide share one duration and easing, so the beak stays on the handle. Measured in all four
  corners: ≤ ±12 px horizontally (handle 22 px wide), ±1 px vertically, 0 px at start and end.
- Corners: `bottom-right` (default), `bottom-left`, `top-right`, `top-left`. The art faces right; in
  right corners it is mirrored about its centre so the robin looks into the screen.
- Shown at 160 × 136 px, 16 px from the edges. Panel: full height, `min(420px, 100vw − 24px)` wide;
  closed panel content is `inert`. Escape closes. Tunables (CSS variables): `--qf-grab-ms`,
  `--qf-pull-ms`, `--qf-pull-ease`, `--qf-mascot-w`, `--qf-panel-w`.

### The chat panel
Header (robin icon, "Q-FIT"), messages (user right, answers left; knowledge-base fallback answers have
an orange left border and a notice), collapsible "Belirsizlikler/Caveats" and "Kaynaklar/Sources", an
"AI explanation" label on model text, a textarea (Enter sends, Shift+Enter new line, 2000 characters).
Text is escaped; only `**bold**` is rendered. The last 10 turns are sent as `history`.

---

## 7. How to integrate it into the team's React + Three.js app

1. **Copy** `QFIT-AI/mascot/react/src/qfit/` into the app's `src/` (keep the folder together; it
   needs React 18+ and a bundler that imports `.png` and `.css`, e.g. Vite).
2. **Render** the assistant once, above the 3D canvas:

```tsx
import { QFitAssistant } from "./qfit/QFitAssistant";
import type { FocusMapPayload, QFitAction, QFitResponse } from "./qfit/api";

<QFitAssistant
  corner="bottom-right"
  lang="tr"                                          // or omit: browser language
  context={{ ra: cameraRa, dec: cameraDec, fov_deg: camera.fov }}   // what the view shows NOW
  onActions={(actions: QFitAction[]) => {
    for (const a of actions) {
      if (a.type === "focus_map") {
        const p = a.payload as unknown as FocusMapPayload;
        flyCameraTo(p.ra, p.dec);                    // the team's camera move
      }
      if (a.type === "display_image") { /* products[].preview_url -> showPreview() below */ }
    }
  }}
  onResponse={(r: QFitResponse) => {/* optional: feed the team's data panels from r.data */}}
/>
```

3. **Camera direction ↔ RA/Dec:** use `raDecToDirection(ra, dec)` from `api.ts` (unit vector for a camera
   at the origin looking outwards; y up; RA increases towards −z so east is to the left, as in the real
   sky). If the team's sky texture/model is oriented differently, change only that function. Inverse,
   for `context`:

```ts
const dir = new THREE.Vector3(); camera.getWorldDirection(dir);
const dec = THREE.MathUtils.radToDeg(Math.asin(dir.y));
const ra = (THREE.MathUtils.radToDeg(Math.atan2(-dir.z, dir.x)) + 360) % 360;
```

4. **Image previews on the sky:**

```ts
import { apiUrl, fetchPreviewInfo, raDecToDirection } from "./qfit/api";
async function showPreview(previewUrl: string, scene: THREE.Scene, radius = 850) {
  const info = await fetchPreviewInfo(previewUrl);
  const c = info.corners_radec;
  const pts = [c.top_left, c.top_right, c.bottom_right, c.bottom_left];
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(
    new Float32Array(pts.flatMap(([ra, dec]) => raDecToDirection(ra, dec).map(v => v * radius))), 3));
  g.setAttribute("uv", new THREE.BufferAttribute(new Float32Array([0, 1, 1, 1, 1, 0, 0, 0]), 2));
  g.setIndex([0, 1, 2, 0, 2, 3]);
  const tex = await new THREE.TextureLoader().loadAsync(apiUrl(info.png_url));
  tex.colorSpace = THREE.SRGBColorSpace;
  scene.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, depthWrite: false })));
}
```
   Previews are 0.1–1° wide: when showing one, turn the camera to it and narrow the field of view to
   about three times its size, or it is a few pixels in a 60° view.

5. **Backend URL:** in development proxy `/chat`, `/health`, `/api` to `http://127.0.0.1:8000`
   (Vite `server.proxy`); in production either serve front end and API from one domain, or build with
   `VITE_QFIT_API=https://<api host>` and add the site origin to `CORS_ORIGINS`.
6. **Data panels** (observations table, periods timeline, spectra) belong to the UI team; take the data
   from `onResponse` (`data.observations`, `data.observation_periods`, `data.spectral`,
   `data.image_products`, `object`). Label pixel samples "raw pixel value (MJy/sr), not the object's
   flux" and time gaps "not observed".
7. **No React?** `mascot/vanilla/`: `<link rel="stylesheet" href=".../mascot/vanilla/qfit-widget.css">`,
   `<script src=".../mascot/vanilla/qfit-widget.js"></script>`, then
   `new QFitWidget(element, { api: "http://127.0.0.1:8000", corner: "bottom-right", lang: "tr" })`;
   methods `setContext({...})`, `setCorner(...)`, `toggle()`; event `qfit:response` on the element.

---

## 8. Rules for the merge (do / do not)

**Do**
- Keep `QFIT-AI/` as one folder; keep `.github/workflows/qfit-ai.yml` and `LICENSE` at the repository root.
- Send the camera's current RA/Dec (and field of view) as `context` with every question.
- Keep the robin's z-index above the 3D canvas and check no team UI covers its corner.
- Keep the thinking state for the whole wait (answers can take up to ~90 s when the archive is slow).
- Run `pytest` in `QFIT-AI/` and the app's build after merging.

**Do not**
- Do not put `OPENAI_API_KEY` (or the team token) in any front-end file or environment variable that
  ships to the browser (`VITE_*` variables are public).
- Do not edit the AI rules, the prompts, the tool list or the envelope shape to make the UI easier;
  adapt the UI to the contract instead (`docs/API_CONTRACT.md`).
- Do not show model text as data, or a preview as a measurement, or a candidate as a discovery.
- Do not run the backend with several workers, and do not delete `research/` (the knowledge base).
- Do not recolor or redraw the robin art; animate with transforms on top of it.
- Do not rename `mascot/react/src/qfit/assets/*` (the CSS references them).

---

## 9. Not done yet / known limits
- `research/data.json`, the timeline components and `/predict` (phase descriptions, thresholds) belong to
  the team and are **not implemented**: no field names or thresholds were guessed.
- The RA/Dec ↔ camera convention must be checked against the team's real sky scene.
- Hosting is not chosen; `Dockerfile` exists but was never built (Docker was not available).
- The team token proves "a team member", not "which" member; reviewer names are self-declared.
- On 2026-11-14 SIMBAD was down all day and IRSA had intermittent 502/503 errors; the system handled both
  (Sesame fallback, honest "archive unavailable" answers, BLOCKED live tests).
- Two navigation examples in the dataset (Betelgeuse, TR/EN) await human review.
- The thinking animation's robin is drawn in a slightly different style and low resolution (182 px);
  a matching high-resolution redraw would help.

## 10. Where to read more (all in `QFIT-AI/docs/`)
`API_CONTRACT.md` (endpoints, envelope, errors) · `FRONTEND_CONTRACT.md` (React/Three.js integration,
previews, CORS) · `MASCOT_AND_CHAT_UI.md` (assets, states, beak pull) · `AI_ARCHITECTURE.md` (agent,
RAG, grounding, providers) · `DEPLOYMENT.md` (hosting, HTTPS, cost protection) · `MODEL_EVALUATION.md`
(measurements) · `AI_TRAINING_PIPELINE.md` (dataset; no model weights are trained) ·
`SCIENTIFIC_SOURCES.md` (source registry) · `../HANDOFF.md` (Turkish work log, round by round).
