# Current verification evidence — 2026-11-14

This report records the current integration. Historical source evidence remains in the preserved input archive and is not current Web/Three.js acceptance.

## Automated checks

| Check | Observed result | Machine-readable evidence |
|---|---|---|
| Backend | 178 passed, 4 live-only skipped, zero failures/errors | `reports/backend-validation.json`, `reports/backend-tests.xml` |
| Frontend | 166 passed, zero failed/skipped | `reports/frontend-validation.json`, `reports/frontend-tests.json` |
| TypeScript / build | Exit 0 | `reports/frontend-validation.json` |
| Lint | Exit 0; 12 warnings, chiefly existing hook/ref/Fast Refresh recommendations | `reports/frontend-validation.json` |
| Main JS | 362744 bytes; 112438 gzip bytes (Python gzip level 9); lazy Three runtime separate | `reports/frontend-validation.json` |
| Motion | 20 independently generated Astropy golden positions within 1e-9 pc | `astrometry.test.ts`, `reports/THREE_EVIDENCE.md` |
| Colour | Eight supplied Python golden cases exact in every sRGB channel | `blackbody.test.ts` |
| Expanded models | 18 numerical/scene/serialization tests + 2 source/uncertainty/language UI tests | `stellarModels.test.ts`, `ui.test.tsx` |
| Exported Three.js assets | Five ObjectLoader round-trips, byte-identical re-export, 10 local HTTP bodies matched | `reports/model-assets-validation.json`, `reports/model-http-local.json` |
| Native shader syntax/link | Seven GLSL ES 3.00 programs passed with Three r170 chunks; no GPU rendering claim | `reports/model-shaders.json` |
| Updated knowledge/seed contracts | Six delivery tests passed after the documentation bundle update | `backend/tests/test_delivery.py` |
| Public seed | Five ready sequences and all raw cutout SHA-256 hashes verified | `docker/verify_seed.py`, `reports/docker-release.json` |
| macOS launcher | Fresh virtual environment installed the pinned dependencies; empty data directory initialized and all five ready targets returned HTTP 200 | `reports/local-package.json` |
| HTTP/containers | New revision: 32 static files and five ready IDs; unchanged scientific-image baseline retained | `reports/docker-models.json`, `reports/docker-release.json` |
| Local API performance | Real HTTP timings/concurrent requests, not GPU/first-paint timing | `reports/performance.json`, `reports/performance.md` |
| Palette contrast | Six relevant text/control combinations meet the documented thresholds | `reports/DESIGN_AUDIT.md` |

The early live-archive run failed with upstream HTTP 502. The final SIA/ESA retest passed 3 of 4 cases: actual cutout structure/wavelength verification and both end-to-end pipelines succeeded. One Barnard DR1 discovery query still failed with upstream HTTP 502; see `reports/live-validation.json`, `reports/live-tests.xml` and `reports/live-archive-results.json`. Later, the SIA service recovered. A new arbitrary-coordinate search completed with four real frames; see the dated result below.

Reproduce from the root: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q`; `npm --prefix frontend test`; `npm --prefix frontend run build`; `npm --prefix frontend run lint`. The optional live command is `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests --live -q`.

## B1 mapping (63 rows)

No row below is marked as browser-passed. The third column identifies implementation for review; tested flows are covered by `ui.test.tsx`, command/store tests and the dedicated science tests. Pixel appearance, all breakpoints and interactive GPU rendering remain **unverified**, because the saved browser permission denied local-origin access even after explicit user approval. The numerical/DOM tests do not replace that missing acceptance.

| B1 | Requirement | Implementation evidence | Current acceptance |
|---|---|---|---|
| 1 | Brand/home | `App.tsx` | Code present; browser unverified |
| 2 | Filler header tag removed | `App.tsx` | Code present; browser unverified |
| 3 | Sources dialog | `App.tsx / SourcesDialog` | Code present; browser unverified |
| 4 | TR/EN and URL | `i18n / store.ts` | Code present; browser unverified |
| 5 | Three mode switch and keys | `App.tsx / commands.ts` | Code present; browser unverified |
| 6 | Old filler footer removed | `App.tsx` | Code present; browser unverified |
| 7 | Loading notes | `SkyCanvas.tsx / common.tsx` | Code present; browser unverified |
| 8 | Data-driven intro | `App.tsx` | Code present; browser unverified |
| 9 | Target filter and / key | `App.tsx` | Code present; browser unverified |
| 10 | Targets heading | `App.tsx` | Code present; browser unverified |
| 11 | Target selection, colour and readiness | `App.tsx / blackbody.ts` | Code present; browser unverified |
| 12 | Empty filter result | `App.tsx` | Code present; browser unverified |
| 13 | Expanded target measurements | `App.tsx / TargetMeasurements` | Code present; browser unverified |
| 14 | Spectral class | `App.tsx / TargetMeasurements` | Code present; browser unverified |
| 15 | Distance/parallax/uncertainty | `astrometry.ts / TargetMeasurements` | Code present; browser unverified |
| 16 | Trail toggle | `commands.ts / StarScene.ts` | Code present; browser unverified |
| 17 | Grid toggle | `CelestialSphere.ts / NeighbourhoodScene.ts` | Code present; browser unverified |
| 18 | Hipparcos sky toggle | `CelestialSphere.ts` | Code present; browser unverified |
| 19 | Scale/model/RV notes | `SkyCanvas.tsx / App.tsx` | Code present; browser unverified |
| 20 | Download view and local storage | `App.tsx / commands.ts` | Code present; browser unverified |
| 21 | Source record/file links | `App.tsx` | Code present; browser unverified |
| 22 | Saved status | `App.tsx` | Code present; browser unverified |
| 23 | Coordinate input | `SearchForm.tsx` | Code present; browser unverified |
| 24 | Archive search/job/cancel | `JobPanel.tsx / api.py` | Code present; browser unverified |
| 25 | Real stages and errors | `JobPanel.tsx / errors.ts` | Code present; browser unverified |
| 26 | Archive product summary and provenance | `panels.tsx / Viewer.tsx` | Code present; browser unverified |
| 27 | Persistent canvas | `SkyCanvas.tsx / runtime.ts / engine.ts` | Code present; browser unverified |
| 28 | Source caption | `App.tsx` | Code present; browser unverified |
| 29 | Scene title | `App.tsx` | Code present; browser unverified |
| 30 | Coordinate/epoch subtitle | `App.tsx` | Code present; browser unverified |
| 31 | Computed angular shift | `App.tsx / astrometry.ts` | Code present; browser unverified |
| 32 | Zoom/reset controls | `controls.ts / commands.ts` | Code present; browser unverified |
| 33 | Surface labels | `StarScene.ts / labels.ts` | Code present; browser unverified |
| 34 | Trail dates/year labels | `MotionTrail.ts` | Code present; browser unverified |
| 35 | Compass replaced by N/E guides | `MotionTrail.ts` | Code present; browser unverified |
| 36 | Drag/scroll/key hint | `App.tsx` | Code present; browser unverified |
| 37 | Representative/shared-grid note | `SkyCanvas.tsx / App.tsx` | Code present; browser unverified |
| 38 | Real frame panes | `Viewer.tsx / Pane.tsx` | Code present; browser unverified |
| 39 | Single/side/difference/stack/co-moving | `Viewer.tsx / analysis.py` | Code present; browser unverified |
| 40 | Continuous wavelength readout | `Viewer.tsx` | Code present; browser unverified |
| 41 | Frames/time-stack segment | `App.tsx / TimeStackScene.ts` | Code present; browser unverified |
| 42 | Shared time strip | `App.tsx / Timeline.tsx` | Code present; browser unverified |
| 43 | Year or UTC value | `App.tsx / Timeline.tsx` | Code present; browser unverified |
| 44 | Previous/next | `commands.ts` | Code present; browser unverified |
| 45 | Play/pause | `App.tsx / Viewer.tsx` | Code present; browser unverified |
| 46 | Year/frame slider | `App.tsx / Timeline.tsx` | Code present; browser unverified |
| 47 | Year/frame/blink speed | `App.tsx / Viewer.tsx` | Code present; browser unverified |
| 48 | Axis ticks | `App.tsx / Timeline.tsx` | Code present; browser unverified |
| 49 | Stop at 2100 | `App.tsx / commands.ts` | Code present; browser unverified |
| 50 | Sources/limits/licenses/provenance | `SourcesDialog / panels.tsx` | Code present; browser unverified |
| 51 | Dialog close/focus | `common.tsx / Dialog` | Code present; browser unverified |
| 52 | Keyboard map and command validation | `commands.ts / App.tsx / Viewer.tsx` | Code present; browser unverified |
| 53 | Local view download | `App.tsx / storage.ts` | Code present; browser unverified |
| 54 | Live archive search | `JobPanel.tsx / api.py` | Code present; browser unverified |
| 55 | Home shell/tasks | `App.tsx / TutorialPanel.tsx` | Code present; browser unverified |
| 56 | Jobs and insufficient data | `JobPanel.tsx` | Code present; browser unverified |
| 57 | Frame metadata drawer | `Viewer.tsx / panels.tsx` | Code present; browser unverified |
| 58 | Catalogue/mask layers | `Viewer.tsx / Pane.tsx` | Code present; browser unverified |
| 59 | Marks/share/read-only flow | `MarksPanel.tsx / ObservationCard.tsx` | Code present; browser unverified |
| 60 | Light curve/spectrum | `LightCurve.tsx / SpectrumPanel.tsx` | Code present; browser unverified |
| 61 | Difference/stack | `Viewer.tsx / analysis.py` | Code present; browser unverified |
| 62 | URL/target/coordinate/embed | `router.ts / store.ts / App.tsx` | Code present; browser unverified |
| 63 | Shared observation route | `App.tsx / Viewer.tsx` | Code present; browser unverified |

## Actual input data and result limits

The source catalogue contains 120 Gaia neighbours plus five targets. The real Hipparcos sky has 8,785 V<6.5 stars. SPHEREx presets contain 6/6/2/3/8 accepted frames for Barnard/Epsilon Indi/WISE 0855/RW Aur/R Dra respectively, with 25 retained raw cutouts. Preparation reused the supplied, dated inventory to choose real files during the IRSA query outage; it downloaded and processed actual FITS data. The inventory date/hash and raw checksums remain in provenance.

See regenerated `reports/targets/OZET.md`. WISE 0855 is not detected in the adopted frames; R Dra is saturated; no target is scientifically confirmed. All output retains `change_scientifically_confirmed: false`. The linear space-motion model gives Barnard 12.8932 arcmin from 2026 to 2100 (display 12.9′); it does not force the plan's rough 12.8′ approximation.

## Deliverables and unperformed acceptance

- An earlier seven-slide demo deck (BlinkSpace) was prepared from real preset products and catalogue predictions. It is not part of this repository.
- The public-data seed deliberately excludes user observations, editing keys, jobs and searches. It is copied only to an empty runtime data directory.
- An initial limited browser observation saw the early Barnard scene and no console errors, and exposed a stage-height issue later corrected in CSS. The expanded models and that layout correction have not had a complete visual review.
- Remaining: desktop/mobile screenshots, physical device/screen-reader checks, GPU shader/runtime measurements, context recovery, 20-switch browser resource/FPS checks, public hosting/URL, five independent user tests and competition submission.
- No public push, hosting purchase, account creation or message to another person was performed.

Final fresh-coordinate SIA availability probe: 2026-11-14T18:05:57Z; result 200. This is an endpoint-availability check, not a completed new-coordinate processing workflow. See `reports/live-final-probe.json`.

## Final fresh-coordinate workflow

The local application processed an actual new search at RA 202.469575°, Dec 47.195258°, FOV 6 arcmin, maximum four frames. The job queried all configured SPHEREx SIA collections, downloaded real FITS files and completed with `status: ready`, four images and `target_id: null`. Each PNG body decoded successfully, and its source FITS SHA-256 is recorded in `reports/new-coordinate-live.json`. No prepared-target cache or synthetic data was substituted. This confirms the API/pipeline workflow after the earlier archive outage; the browser interaction remains unverified.


## SPHERE-X / QFIT integration evidence

- `reports/integration/regression.json`: automated pass counts, unchanged scientific files/vendor files and additive API comparison.
- `reports/integration/docker.json`: non-root image, default-off assistant, exact HTTP asset bytes, real ready sequences, source cards, CSP and pattern scan.
- `reports/integration/assistant-eval.json` and `assistant_eval.md`: separate real-provider ten-question evaluation, not a claim of new astronomical verification.
- `tools/regress.sh`: reproducible local tests/build/contract/data checks and Docker checks; `--no-docker` explicitly omits the container check.

The original incorrect OpenAPI capture at `/openapi.json` contained SPA HTML; the old server's correct `/api/openapi.json` was captured before restart. It is the immutable baseline used by the contract check. Supplied reference screenshots are historical design inputs, not current browser evidence.

## Three.js revision — 2026-11-15

197 frontend tests and production build passed. Seven exported model shader programs linked. Browser access worked in this session: rendered scenes, independent animation clocks, giant/contraction evolution, coordinate search, 1280×720 and 375×812 layout were inspected. Mobile grid-row clipping and transparent sky depth occlusion were fixed. No console errors/warnings were observed. 141 science files and 198 QFIT vendor files retain their previous hashes. See `reports/evolution-validation.json` and `docs/EVOLUTION_EXPLORER.md`. Prior browser-denial reports are historical; no control was bypassed. No new sustained-FPS, screen-reader, Docker or backend test claim is made.
