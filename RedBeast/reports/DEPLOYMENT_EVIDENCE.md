# Delivery and assistant evidence

Recorded during implementation. These checks apply to this work,
not to screenshots or test counts inherited from the imported project.

## Completed checks

- Docker Desktop engine responds as version 29.7.2.
- `docker compose config --quiet` passed.
- Python compilation of the assistant, seed tools and container scripts passed.
- `sh -n docker/entrypoint.sh` passed.
- `pytest tests/test_assistant.py tests/test_delivery.py -q`: **24 passed** on Python 3.13.
  Tests cover the disabled main-application routes, mock SSE and manual tool results,
  confirmation metadata, context/history limits, rate/daily counters and lack of content
  logging. Seed tests cover exclusion of private records and SQLite free-page remnants,
  original-data preservation, existing-directory protection, missing-file rejection and
  rejection of raw files whose SHA-256 checksum is wrong.
- The deterministic knowledge bundle contains 91 source-hashed chunks and 71,490 UTF-8
  text bytes. This is the actual supplied material, not padded to a nominal token target.
  The five target reports were regenerated from the fresh real-data presets; source dates remain explicit.
- The English README and Turkish README describe current setup and distinguish local
  validation, independent user tests and public deployment.
- The current AI disclosure identifies OpenAI Codex assistance and separately describes
  the imported source's historical attribution.
- The independent-user-test form now includes G9 and G10. **No human tests were run.**

## Container checks

A fresh `blinkspace:smoke` image built successfully with the current dependency lock as
constraints. It runs as the non-root `app` user on the deliberately changed `PORT=8123`,
published only to local port 18080. Docker reports the health check as **healthy**.

Actual HTTP checks (full response bodies, not just status codes):

- `/api/health`: 200, pipeline 1.2.0, no active jobs.
- Frontend HTML:200, 2,338 bytes, same-origin script/connect CSP.
- `/api/motion`: 200, 146,768 bytes, one-day public cache.
- `/api/sky/bright.json`: 200, 99,393 bytes, one-day public cache.
- `/api/sky/bright.bin`: 200, 245,980 bytes, one-day public cache.
- Assistant status:disabled/null; a valid chat request returns 503 assistant_disabled.
- `/api/targets`:five targets, zero ready sequences in this intentionally unseeded image.

The smoke build explicitly uses `BLINKSPACE_BUILD_SEED=0`. It does not satisfy the
five-preset release acceptance check. Full release seed verification remains separate.
The machine-readable result is `reports/docker-smoke.json`.

An initial packaging defect was found and fixed: atomic scientific JSON files used mode 0600,
while the image copied them as root and ran uid 1000. `COPY --chown=app:app` now gives the
runtime ownership of its public code/resources. The scientific writer also now uses 0644.
The API uses pure ASGI header middleware to preserve streaming and error propagation.
Earlier builds stopped on in-progress frontend type errors, which were subsequently fixed.

Base image digests downloaded for this run:

- `node:22-slim`: `sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee`
- `python:3.13-slim`: `sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90`

## Hosting research and remaining external actions

Official provider documentation was checked on 14 November 2026. New Hugging Face Docker
Spaces require a paid account plan even though CPU Basic has no hourly charge. Render's
free web services sleep after 15 minutes, provide 750 instance hours per workspace monthly
and lose local filesystem changes. Details and source links are in `docs/DEPLOY.md`.

No public deployment, repository publication, FortiGuard classification request or
competition submission was performed in this work. No paid hosting resource was started.
A final public URL is required before recording those external checks. Five independent
user tests and judging submission remain real-person/account steps.

## Streaming mock and static assets

A separate temporary container with the local mock enabled returned the expected SSE
sequence (`text`, `command`, `sources`, `done`). The fixed `mock:save` scenario proposed
`save_view` with confirmation required. The container was removed after the check.
`reports/docker-mock.json` records the result. The production-default smoke container
keeps the assistant disabled. Its main JavaScript (354,147 bytes) and CSS (35,814 bytes)
both returned complete HTTP 200 bodies after the ownership fix.

## Public seed and English demo deck

The public seed was exported from the current five ready pipeline 1.2.0 sequences.
`docker/verify_seed.py seed-data` passed, including all raw FITS SHA-256 checks, processed
PNG/mask/NPZ files and precomputed track-file presence. Export uses a separate SQLite backup,
removes private observations, edit tokens, jobs and search records, and compacts the seed
database. The source runtime database remains unchanged. Release HTTP validation follows
the final application build.

An earlier deck (`BlinkSpace-Demo-EN-Reviewed.pptx`, not part of this repository) contained seven English slides, two real
processed SPHEREx frame previews and two editable charts of catalogue motion predictions.
The observations and predictions are explicitly distinguished. The final file was imported
and all seven rendered slides visually reviewed; the slide count, layout and package checks
passed. Its image parts contain 3,293 and 3,383 bytes. No native PowerPoint execution or
application screenshot review is claimed. UI browser preview remains separately blocked
by the host application's saved permission policy.

Final deck SHA-256: `001f379849f9e355ef353a79c32b2145b42c0976c95dc7a74dd454a01f31693a`.
Size: 55,556 bytes. Independent user tests and public deployment remain pending.

## Final seeded release verification

The final `blinkspace:release` image builds successfully and runs as uid 1000 with `PORT=8125` on localhost port 18084. `reports/docker-release.json` records exact body hashes for the delivered motion, sky and physical-model catalogues, every static asset/font, all 25 preset PNGs and 15 derived PNGs (difference, ordinary stack and co-moving stack across five targets). All five ready IDs and track lengths match. The assistant is disabled and chat returns 503. The copied seed passes every raw-cutout SHA-256 check and contains zero observations, jobs, searches and query/catalogue-cache rows.

A final build exposed that frontend contract tests import the published JSON resources. The Docker web stage now copies those exact resources for TypeScript verification, so a clean container build no longer depends on files outside its build stage. Browser visual/GPU acceptance remains separately unverified.

## Reusable-model release rebuild

After the new model factory and exporter were integrated, `blinkspace:release` was rebuilt
from the pinned dependencies. The build regenerated and ObjectLoader-parsed all five
assets without an archive request and verified the unchanged public seed. A fresh uid-1000
container returned all **32** compiled files with byte-for-byte agreement to the local
build, including the five models, animation module and model instructions. All five
ready preset IDs were present. See `reports/docker-models.json` for the new image ID and
file hashes. The earlier `docker-release.json` retains the full scientific-image baseline;
those unchanged pipeline calculations were not rerun for this frontend revision. The
new test container was stopped after verification. No public deployment was performed.
