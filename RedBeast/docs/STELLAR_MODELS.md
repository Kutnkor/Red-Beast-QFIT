# Stellar surfaces and surroundings

The five target models use the cited parameters in `backend/blinkspace/resources/stellar_profiles.json`, served by `/api/models`. Each parameter retains its unit, uncertainty or range where supplied, evidence class, source and limitations. The interface shows these in English and Turkish. Unknown radius or temperature remains unknown.

| Target | Displayed structure | Evidence and limits |
|---|---|---|
| Barnard's Star | Granulated photosphere, coronal shell, magnetic arches and radial wind tracers | Radius 0.187 ± 0.001 R☉, temperature 3195 ± 28 K from the [2024 ESPRESSO study](https://arxiv.org/html/2410.00569v1). [Chandra/Hubble observations](https://www.chandra.si.edu/photo/2020/barnards/index.html) support magnetic activity; the drawn shell and wind are qualitative. No measured field map, wind speed, flare event or planet is invented. |
| Epsilon Indi Ba/Bb | Two separate surfaces, layered advecting clouds and illustrative orbit | 1320 K and 910 K are display midpoints of [BT-Settl model ranges](https://arxiv.org/abs/0911.3143), not new measurements. Each atmosphere follows its own component. The eccentricity and inclination use the [published orbit](https://arxiv.org/pdf/2205.08077); phase, display separation, equal component size and symmetric placement are illustrative. SPHEREx does not resolve the two components. |
| WISE 0855 | Very dark surface, representative cloud bands and thin atmosphere | The adopted 250 K historical reference and later model-dependent analyses are linked in the profile. Visible emission is negligible. The renderer deliberately uses a dark placeholder, not a visible-light photograph or a measured infrared surface map. No physical radius is adopted. |
| RW Aurigae | Flared accretion disk, funnel flows onto the star, differential disk flow, dust contrast and two jet tracer streams | The cited stellar and ALMA measurements describe RW Aur A. [GHOsT spectroscopy](https://arxiv.org/abs/1909.10392) constrains gas in its jet. The drawing illustrates A; SPHEREx blends A and B. Star, disk and jet display scales differ. Particle speeds and densities are not inferred measurements. |
| R Draconis | Large convection cells, irregular molecular layers, a radius/temperature/colour cycle and extended outflow | The 511 ± 142 R☉ and 2034 ± 139 K values are [historical, phase-specific K-band estimates](https://arxiv.org/abs/astro-ph/0210167), not a current photospheric radius or cycle average. GCVS supplies the 245.6-day period. Outflow is a class illustration, not a measured dust quantity. The SPHEREx sequence is saturated. |

## Display choices

- Physical radii, when adopted, use `sqrt(R/R☉)` display units, with a solar reference in the context view. Close-up framing excludes that reference. Unknown single radii use one representative unit; the two unknown binary radii use 0.55 units each. These are separate from the astrometric trail's ×600 scale.
- Photospheric colour uses the existing Planck/CIE/Wyman calculation. Unknown temperatures use a neutral colour. Below 1000 K, the clamped colour is strongly dimmed and explicitly labelled as emitting almost no visible light.
- Eddington limb darkening gives surface depth. Convection cells, cloud bands, accretion polar structure and disk density patterns are procedural, representative structure, not telescope imagery.
- The Mira cycle uses a deliberately illustrative ±5.5% display-radius variation and ±4% temperature excursion. The contraction/heating phase, eight-second cycle and display intensity are not fitted to the SPHEREx light curve. Colours interpolate precomputed blackbody endpoints to avoid an unbounded per-frame temperature cache.
- Disk angular flow decreases with radius as `r^-3/2`; radial wind and bipolar jet particles show direction. Their dimensions, speed and density do not form a fluid or magnetohydrodynamic solution.
- The calendar controls the catalogue's linear space motion. It does not evolve a star's age or predict its future surface. The separate illustrative animation clock advances only with the Surface & flow animation control. It is independent of calendar playback. Pause and reduced-motion preference freeze that clock.
- Surroundings can be hidden without hiding the photosphere or motion trail. A target change disposes its prior disk, atmosphere, jets and secondary component.

## Reusable Three.js models

The live scene now uses five named model recipes through `createStellarModel` in
`frontend/src/three/models/StellarModel.ts`. The same factory exports five `.three.json`
assets in `frontend/public/models/`. The selected target's measurement panel has a
localized model-download link. Each asset contains geometry, procedural materials,
embedded halo texture, adopted parameters, sources, caveats and animation metadata.

`animate-stellar-model.js` updates an ObjectLoader-loaded model with the same animation
code as the live scene. `faceStellarModel` keeps reference circles camera-facing and
caps particle pixel scaling at two. `display_extent` includes vertex-shader outflow;
a static geometry bounding box alone would miss those particles. The model pack README
includes integration instructions. This is the pinned r170 ObjectLoader format, not GLB.

Barnard's added arches use a dipole-like geometric construction. Its magnetic topology
is unknown: even the cited [Barnard wind study](https://arxiv.org/abs/1901.00219) uses
proxy magnetic maps. The new arcs are not measured lines or a claim about particular
flares. RW Aur's funnel paths, disk thickness and corrugations are class illustrations;
all disk, funnel and jet structures share one local orientation. The cited disk angle
does not measure the field map. Brown-dwarf cloud opacity and Mira envelope clumping
are also schematic. None of these new structures changes measured SPHEREx pixels.

`npm run models:export` produces deterministic scene identifiers and file hashes, checks
all position values are finite, and parses all five results through ObjectLoader. It
exports reduced geometry while retaining the full procedural materials. The live app
continues to use its selected geometry-quality setting. `npm run build` regenerates the
assets automatically; the build has no archive or model-provider dependency.

## Verification

`frontend/src/tests/stellarModels.test.ts` exercises the actual delivered profiles and motion catalogue: unknown values, class selection, compressed radii, Kepler extrema, wide/narrow camera fitting, binary atmosphere attachment, resource disposal, layer isolation, pause, reduced motion and idle update termination. Two UI tests verify uncertainty, source limitations, component temperatures and Turkish formatting. These are numerical/component checks, not a GPU or visual acceptance test.

The profile builder is reproducible with `PYTHONPATH=backend python -m tools.build_stellar_profiles`. Backend tests reject uncited measurements, promoted unknown values and a false stellar-evolution clock. The fetched GCVS response is bundled with its SHA-256 and parsed period.

## Separate evolution explorer

See [EVOLUTION_EXPLORER.md](EVOLUTION_EXPLORER.md) for the newly authorized published-track lifecycle view, separate clocks, layout/occlusion fixes, coordinate search and explicit model limits. Surface contrast is now enhanced for inspection with advecting granulation and darker inter-cell lanes; this remains illustrative, not a measured contrast map.
