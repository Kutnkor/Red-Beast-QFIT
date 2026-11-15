# V4 interface, Three.js and API audit — 15 November 2026

The active interface remains the supplied V4 design. RedBeast is the application name;
QFIT is the assistant. The default view is actual SPHEREx observations. This audit records
developer checks, not a guarantee that every possible bug is absent.

## Fixed interactions

- Catalogue, published evolution and education modes share one state model. Switching views
  pauses the old clock, preserves the selected target and restores the appropriate model.
- All five SPHEREx targets link to supported comparison tracks: Barnard → BHAC15 0.15 M☉,
  Epsilon Indi B → ATMO 0.05 M☉, WISE 0855 → ATMO 0.005 M☉, RW Aur → MIST 1.4 M☉,
  R Dra → MIST 1 M☉. These are comparison tracks, not measured ages or fitted futures.
  Brown dwarf cooling and binary-component limitations are explicitly labelled.
- The mobile layout uses document flow. An invisible decorative layer that intercepted
  model-button taps was removed from hit testing. Hidden image panels no longer cover 3D.
- Education pause and language switching preserve animation time. Reduced-motion settings
  reach the scenes, and background tabs stop rendering. Target hover no longer resets the
  neighbourhood camera. Late failures from obsolete scene imports cannot cover a newer scene.
- Observation analysis opens the shared QFIT assistant with the selected context. Existing
  legacy analysis and image-comparison controls remain connected.

## Lifecycle visuals

Three.js now includes illustrative protostar accretion funnels/disks, magnetic arches,
diffuse expanding nebula/supernova shells, neutron-star beams and black-hole accretion disks.
Transitions ease radius, temperature and luminosity visually while retaining the source
table readouts. Canvas proportions follow their container. Pause, reduced-motion and
context-recovery paths are handled explicitly.

The gas, fields and flows are illustrative rather than hydrodynamic simulations or resolved
SPHEREx images. The full education ruler is separate from MIST/BHAC15/ATMO tables. General
morphology references: [NASA stars overview](https://science.nasa.gov/universe/stars/),
[NASA Sun-like lifecycle](https://science.nasa.gov/resource/the-life-cycle-of-a-sun-like-star-annotated/),
[NASA stellar lifecycles](https://imagine.gsfc.nasa.gov/educators/lifecycles/LC_main3.html).
Exact input tables and target limitations remain in the existing scientific documentation.

## Verification

| Check | Result |
| --- | --- |
| Frontend regression suite | 217 passed, 0 failed |
| Python ordinary suite | 204 passed; 4 live tests skipped by design |
| Real archive suite, launcher configuration | 4 passed in 74.44 seconds |
| Production build and TypeScript | Passed; existing bundle-size warning remains |
| Lint | Exit 0; prototype/React warnings remain |
| Python HTTP service | Health OK; five ready targets, 25 real observation frames |
| Desktop | Published RW Aur model, education phases, TR/EN, observation panels, search and QFIT bridge checked |
| Mobile | 390px layout and actual model-button interaction checked; no horizontal overflow |
| Final inspected browser console | No errors or warnings |

The live suite reads the real archive into fresh temporary storage. It covers product
discovery, actual FITS layers/wavelength/footprint, a preset pipeline and an arbitrary
coordinate pipeline. The final command uses the same providers as the launcher:

```bash
cd backend
BLINKSPACE_ARCHIVE_PROTOCOL=sia BLINKSPACE_GAIA_PROVIDER=esa \
BLINKSPACE_ALLWISE_PROVIDER=vizier ../.venv/bin/python -m pytest --live tests/test_live_archive.py
```

Earlier diagnostics using SIA alone stalled or failed with the default IRSA Gaia mirror;
two reruns were interrupted. They are not counted as passes. The official TAP discovery
probe in `auto` mode now falls back after a bounded 20-second attempt. Explicit TAP mode
keeps its configured timeout. External service availability is still a runtime dependency.

Machine-readable results: [validation.json](../reports/ui-audit/validation.json).
The repository delivery includes raw test reports in `reproducibility/validation`.
Screenshots: [published model](../reports/ui-audit/published-rw-aur.jpg),
[nebula](../reports/ui-audit/education-nebula.jpg), [Turkish interface](../reports/ui-audit/education-tr.jpg).

There is no fresh paid AI evaluation, quantitative FPS/memory benchmark, independent user
acceptance study or public hosting claim. GitHub delivery is recorded separately from a
running public API. Previous reports and the demo presentation retain their original dates.
