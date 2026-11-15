# Scientific 3D implementation evidence

This report distinguishes code/test evidence from browser measurements; unperformed measurements are not claimed as passed.

## Implemented

- One persistent `WebGLRenderer`, dynamically imported, with demand rendering, resize handling, context-loss/recovery handlers and an accessible data fallback.
- Separate lazy scene modules for the representative stellar surface, the actual Gaia neighbourhood, and dated SPHEREx image planes. Scene resources are cached after their first use and disposed when the application closes or source content changes.
- ACES tone mapping, sRGB output, DPR capped at two, and adaptive quality thresholds after 60 consecutive interaction/animation frame timings. Idle gaps are excluded from timing samples. A `?quality=high|medium|low` override is respected.
- Real Hipparcos binary positions and B−V-derived colours, with no invented background stars; camera translation does not introduce background parallax. Grid positions, equator and cited J2000 obliquity define the coordinate overlay.
- Eddington limb darkening and low-contrast representative granulation. The later user request adds class-specific cloud flow, convection, disk/jet/wind tracers and a schematic Mira radius/temperature cycle, detailed in `docs/STELLAR_MODELS.md`. There are no invented planets, measured flare maps or bloom. Unknown temperatures use neutral colour. Objects below 1000 K use 8% of the clamped 1000 K colour and an explicit visible-light limitation.
- Computed Cartesian-motion trails, ten-year ticks, actual SPHEREx MJD dates, a representative surface outline, local N/E guides and a Sun-direction guide.
- Real-neighbour positions at the selected year; absolute-G display brightness, 5/10 pc rings, point picking within six CSS pixels and an accessible name selector. A target outside the displayed neighbourhood is represented by a labelled direction ray, never a false nearby position.
- SPHEREx planes use nearest filtering and transparent invalid pixels. Plane depths preserve real temporal spacing. Predicted tracks, measured centroids and error circles are distinct. Missing measurements are explained. User tracks are dashed and explicitly unverified.
- Camera actions are delivered by the shared command layer through `blinkspace:camera`. Face-on alignment uses the same pixel-centre convention and orientation as the 2D viewer.

## Reproducible checks completed

Command, from `frontend/`:

```sh
node node_modules/vitest/vitest.mjs run src/tests/astrometry.test.ts src/tests/blackbody.test.ts src/tests/sky.test.ts
node node_modules/oxlint/bin/oxlint src/three src/tests/astrometry.test.ts src/tests/blackbody.test.ts src/tests/sky.test.ts
```

Result: **44 tests passed in three files**. The owned Three.js and science files passed Oxlint without warnings. Project TypeScript compilation also passed after integration with the app shell.

- All 20 positions (five targets × four epochs) match independently generated Astropy Cartesian coordinates within `1e-9 pc`, using the plan's explicit `(ICRS x, ICRS z, ICRS y)` mapping.
- All eight supplied Python blackbody golden cases match every 8-bit sRGB channel exactly, including clamping and ties-to-even rounding.
- Invalid temperatures and missing B−V do not fabricate a physical temperature.
- Flux ratios, absolute magnitude, bounded monotonic asinh intensity, poles, equinoxes and graticule unit vectors are checked.
- Time-stack tests cover unequal observing intervals, non-square images, FITS pixel centres, north-up/east-left orientation and a known sky-coordinate round trip.

## Verified difference from the plan's approximate number

The specified Cartesian model and independent Astropy reference give Barnard's Star a **773.5937236354 arcsec** displacement from J2026.0 to J2100.0, bearing **355.5766844063 degrees**. This is **12.8932287273 arcmin**, displayed as **12.9′ north**, rather than the plan's approximate 769 arcsec / 12.8′. The measured radial velocity introduces perspective effects through Cartesian propagation. Source positions and velocities have not been modified to force the approximate number. Relative to the supplied NASA reference of 1896 arcsec, the displacement is about **40.8%** of the lunar diameter.

## Sources and scope

- The supplied `starsim/color.py` is ported by algorithm only; the unrelated stellar-evolution simulation is not imported. Its colour-matching reference is [Wyman, Sloan & Shirley (2013)](https://jcgt.org/published/0002/02/01/).
- The astrometry implementation uses the supplied catalogue and [Astropy's Cartesian velocity conventions](https://docs.astropy.org/en/stable/coordinates/velocities.html). Missing radial velocity is explicitly assumed zero. No observer motion or annual parallax is modelled.
- Unit conversions are fixed astronomical unit definitions; the backend publishes their citation and values in the motion catalogue's `reference` object. The source-backed Moon and obliquity values are read from that catalogue, with no silent fallback.
- The B−V temperature helper follows [Ballesteros (2012)](https://doi.org/10.1209/0295-5075/97/34008).
- Renderer colour-management and lifetime behaviour follow the pinned Three.js r170 implementation; current API reference: [WebGLRenderer](https://threejs.org/docs/pages/WebGLRenderer).

## Browser acceptance still to measure

The 44 unit checks do not prove GPU performance, visual quality or context restoration. Record the actual results for desktop/mobile screenshots, 20 mode switches, idle draw counts, context loss and restoration, first scene loading, and frame rate in the main performance report after running the integrated application. The live canvas exposes `data-rendered-frames`, `data-geometries`, `data-textures`, `data-scene-ready` and `data-quality` for repeatable inspection. No midrange-computer performance claim is made without testing that hardware.

## Integrated regression baseline before the expanded stellar-environment request

The complete frontend suite passed **146/146 tests in 12 files**. This includes the original scientific/viewer behaviours, updated workspace navigation, ready/unready target workflows, real job-stage reporting, one-shot coordinate URL searches, shared read-only observations and their notes, command confirmation/validation, assistant-context privacy and UTF-8 byte limits, and view-URL/state subscriptions. TypeScript compilation and Oxlint checks for the modified Three.js and test files passed.

A limited initial browser observation showed the default Barnard model with visible limb darkening, static granulation, a trail and labels, with no console errors. It also identified an oversized stage height that was reported for correction. The browser work then stopped when the primary approval flow rejected further origin access. This initial observation is not a completed visual, responsive, performance, or context-recovery acceptance test. No screenshot artifact is claimed for that observation.

The user's subsequent request explicitly expands the visual scope beyond a plain representative sphere to source-labelled, target-specific stellar surfaces and environments. The baseline results above predate that expansion; new model work must be checked separately and labelled according to its evidence.

## Expanded model checks completed

The expanded implementation passes 11 model/scene tests using the actual five profiles and delivered catalogue. These check distinct components and their attached atmospheres; disposal of old environments; pause, reduced-motion and idle update behaviour; physical-value unknowns; square-root scaling; Kepler extrema; and wide/portrait camera bounds. Two additional shell tests verify displayed uncertainty, English source caveats, Turkish values and binary component temperatures. The complete current frontend suite has **159 passing tests**. TypeScript and the production build pass. See `frontend-validation.json` for exact exit codes, warning count and bundle size.

These checks do not compile shaders on a real GPU or resolve the saved browser-permission block. Desktop/mobile screenshots, visual appearance, WebGL context recovery, measured FPS and browser memory across 20 switches remain unverified.

## Reusable model revision

The live scene and the five downloadable r170 `.three.json` files now share one factory
and animation module. New geometry includes Barnard's illustrative magnetic arches,
advection in layered brown-dwarf clouds, RW Aur's disk-to-star funnels and flared disk
skin, and R Dra's irregular molecular shells. One local orientation keeps disk, funnels
and jet poles aligned. Camera-facing reference circles survive ObjectLoader loading,
and particle sizes follow the capped renderer pixel ratio.

The full frontend suite passes **166 tests**. Its 18 stellar-model checks include all five
ObjectLoader round-trips, metadata preservation, the same animation before and after
serialization, class-specific structures, camera references and resource disposal. Two
model UI tests also verify target-specific downloads in English and Turkish. TypeScript
and production builds pass; changed model files have no lint warnings. The full lint run
retains 12 existing recommendations. Vite warns that the lazy Three runtime exceeds 500 kB;
this is not an assertion of measured GPU performance.

All five exports are byte-identical on a second run. The real compiled and development
servers each return all five exact model bodies over HTTP. Native glslang 16.6.0 parses
and links seven unique GLSL ES 3.00 programs with the pinned Three.js chunks, ACES tone
mapping and sRGB output. This verifies syntax and shader-stage interfaces, **not browser
WebGL driver compilation, pixels or FPS**. No browser restriction was bypassed.

Evidence: `reports/model-assets-validation.json`, `reports/model-http-local.json`,
`reports/model-shaders.json`, and `reports/frontend-validation.json`. Export instructions
and the reusable animation example are in `frontend/public/models/README.md`.
