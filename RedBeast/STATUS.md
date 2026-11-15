# Current status — 15 November 2026

The active design is **V4**, with the RedBeast brand and the QFIT assistant. The default
view is real SPHEREx observations. Catalogue graphics, published comparison tracks and
illustrative education scenarios have separate controls and clocks. Python serves the
API and built frontend together. See [API documentation](docs/API.md) and
[current audit](docs/UI_AUDIT.md).

Current local automated checks: **217 frontend tests passed; 204 backend tests passed,
4 opt-in live tests skipped in the ordinary suite**. The production build and type check
passed. Desktop and mobile interaction checks cover mode transitions, five target/model
mappings, observations, model playback, coordinate search, bilingual controls and QFIT.
Current screenshots are in `reports/ui-audit/`. Fresh upstream archive results are recorded
separately in the audit; cached seed checks are not described as live downloads.

This source is being prepared for `RDSsee/Red-Beast-Final-Version-`. A prepared local folder
is not proof of a successful GitHub push or public hosting. Deployment status is recorded
in the repository handoff manifest. Personal credentials remain outside the distribution.

## Design unification pass — 15 November 2026

Every screen of the default shell now uses the V4 language: the observation viewer, Sky,
catalogue star, published model, dialogs, analysis drawer and search share
one component kit (`frontend/src/v4/kit.*`), one palette and one motion vocabulary. Orange is
reserved for "now". The Observations view gained a Blink button and a filmstrip of all real
frames; frame changes remain hard cuts. The Sky view now opens on an illustrated top-down
Milky Way with a "you are here" marker and the targets at their catalogue positions, and flies
down to the measured solar neighbourhood. A simplification pass then removed duplicate buttons
and nested boxes and put the Q-FIT panel back to its original styling. Details, file map,
checks and limits:
[docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md).

A third pass replaced centred pop-ups with docked sheets that grow out of their trigger, gave every
viewer layer its own lane, added a lensed black hole, a richer solar-neighbourhood map, one tour per
page and rule-based navigation for the robin ("take me to the Sun").

Archive jobs no longer hold the single worker: cancel works while the archive is queried, the
wait for a failing archive is bounded, and the job panel says why a job waits.

Checks on the Windows working copy: 225 frontend tests passed; backend 211 passed, 4 live
skipped (photometry falls back to an in-repo implementation where the compiled `photutils`
extension is blocked). A UTF-8 file-reading fault that
broke the assistant's source lookup on Windows was fixed. Not done: public hosting, user
tests, device testing on a phone.

The dated notes below are preserved implementation history. Their older V5, disabled-AI
and browser-access statements do not describe the current V4 revision.

---

# Implementation status — 2026-11-14

Pipeline 1.2.0. This is the current Web/Three.js integration; the imported Unity/source projects are preserved separately. No public release or full acceptance claim is made.

## Completed locally

- React/TypeScript/FastAPI application with one persistent Three.js renderer, stellar model, Gaia neighbourhood and actual SPHEREx time stack.
- Five source-labelled stellar profiles: temperature/size with uncertainty, separate binary atmospheres, clouds, corona/wind, disk/dust/jets and a schematic Mira colour/radius cycle. The calendar remains a linear astrometric model.
- Preserved frame comparison, quality masks, marks, sharing, light curve, spectrum, coordinate searches and teaching tasks; bilingual UI and command/state/URL integration.
- Actual Gaia/Hipparcos catalogues and five real SPHEREx presets, 25 accepted raw FITS cutouts, precomputed tracks and regenerated target reports. A private-data-free seed is included for startup without a new archive query.
- Assistant contract, privacy-limited context and mock SSE; real provider remains intentionally out of scope and disabled.
- Source ZIP, macOS launcher, reproducible Docker image, documentation and a seven-slide English demo.
- Five reusable Three.js models with magnetic arches, layered clouds, disk-to-star funnel flows and irregular molecular shells; target-specific downloads and a portable animation module.

The macOS launcher was also run from a fresh local environment in the permanent project directory. All five presets loaded. Existing local runtime sequences were then preserved; runtime data are excluded from the public source ZIP.

## Verification

| Check | Result |
|---|---|
| Backend automated tests | 178 passed; 4 opt-in live tests skipped in this run |
| Final live archive retest | 3 passed; 1 failed on upstream HTTP 502 (Barnard DR1 query). Actual cutout and both end-to-end pipeline tests passed. |
| Frontend automated tests | 166 passed, including 18 scene/model tests and 2 model UI tests |
| Production build / TypeScript | Passed; model export runs before the build |
| Reusable model files | Five ObjectLoader round-trips, animation/metadata tests and byte-identical re-export passed |
| Native shader syntax/link | Seven programs passed glslang; browser/GPU rendering remains unverified |
| Lint | Exit 0, 12 warnings; see `reports/frontend-validation.json` |
| Source values, blackbody and motion | 20 Astropy positions, 8 exact colour golden cases and public profile tests pass |
| Prepared data | Five presets, FITS SHA-256 checks, real dates and track caches; see release verification |
| Docker release HTTP | New model revision: `reports/docker-models.json`, 32 static bodies and five ready presets; scientific baseline: `reports/docker-release.json` |
| B1 interface checklist | 63 rows mapped in EVIDENCE; browser acceptance not completed |

## Outstanding acceptance

1. The saved browser permission denied local-origin access even after the user approved opening the preview. It was not bypassed. Full visual checks at 1440/1024/375 widths, GPU shader validation, FPS, context recovery, and browser memory across 20 switches remain unverified. A limited initial Barnard observation is described in `reports/THREE_EVIDENCE.md`; it is not full acceptance.
2. Archive availability is intermittent: the final live retest passed 3 of 4 cases; one Barnard query still returned HTTP 502. At 18:05 UTC the SIA endpoint recovered; a fresh arbitrary-coordinate search then completed with four real frames. See `reports/new-coordinate-live.json`. New searches still depend on archive availability.
3. Public hosting, public repository push/visibility, final public demo URL, FortiGuard classification and competition submission have not been performed. A hosting/account decision is still needed; the concrete local artifact is ready to review.
4. Independent user tests completed: **0 of 5**. `docs/USER_TEST.md` remains an honest blank protocol.

## Resume

Read EVIDENCE and `docs/STELLAR_MODELS.md`. Start the delivered package with `Start-BlinkSpace.command`, or use Docker Compose. For development, create `.venv`, install the pinned requirements, and run commands with `PYTHONPATH=backend`. The frontend uses Node 22. Do not confuse imported historical screenshots/test counts with current verification.


## SPHERE-X + QFIT integration handoff

The default shell now follows the supplied v5 glass/dock/timeline design and retains the complete original Viewer, source-cited Three.js models, five presets and data pipeline. `?ui=legacy` retains the earlier shell. The QFIT robin uses the supplied Python agent and its OpenAI gpt-5.4-mini provider through the existing same-origin contract. New assistant tools are read-only local retrieval and manually confirmed UI proposals.

The user's key activates only the private local installation and is excluded from source, reports, image and release ZIP. The distributed application stays off until configured and supplies clearly labelled local source cards without a key. Full test counts, three additive API paths, 141 unchanged science file hashes, vendor integrity, Docker and live-QFIT evaluation are in `reports/integration/`.

New browser screenshots, GPU/FPS measurements and physical-device visual acceptance remain unperformed because the earlier saved browser-access denial was not bypassed. The seven-slide reviewed deck is preserved as historical material; it is not evidence for the new layout. No public push/deployment/submission occurred.
