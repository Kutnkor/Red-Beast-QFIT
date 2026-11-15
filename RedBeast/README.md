---
title: RedBeast
sdk: docker
app_port: 8000
license: mit
---

# RedBeast

A blink comparator for real NASA SPHEREx images, with catalogue-based 3D stellar motion.
Choose Barnard's Star, Epsilon Indi B, WISE 0855−0714, RW Aurigae or R Draconis, or search
an ICRS sky position. Compare actual observing dates at matched wavelengths and inspect
each frame's source, quality flags and processing history.

[Türkçe](README.tr.md) · [Scientific method](docs/METHOD.md) · [Data sources](docs/DATA_SOURCES.md)

The 3D views show computed paths and a representative stellar surface. They are not resolved
images of the stars. Measured, computed, representative and assumed values are labelled.
Invalid pixels remain missing. Different wavelengths are not treated as time variability.
The application never labels a change as scientifically confirmed.

RedBeast (formerly BlinkSpace) is an independent project. It is not developed or endorsed by NASA.

## Latest verification and API

[Design system](docs/DESIGN_SYSTEM.md) · [Current UI/3D audit](docs/UI_AUDIT.md) · [Python API and setup](docs/API.md) · [OpenAPI schema](docs/openapi.json).

## SPHERE-X interface and QFIT

The supplied **V4** is the default interface. It opens **real SPHEREx Observations**. The original V4 gliding tabs, mass ruler, phase timeline, animated cards, HR plot and dock are retained. **Star** offers three explicitly separate views: catalogue-based 3D graphics, published MIST/BHAC15/ATMO comparison tracks, and the original **0.1–100 M☉ illustrative education scenario**, now rendered in Three.js. Educational numbers are not observations or target-fitted predictions.

**Sky** uses catalogue positions and RA/Dec search. **Ctrl/⌘K** opens search and the QFIT robin opens the assistant. The immediately previous React shell remains at `?ui=classic`; the earlier data workspace remains at `?ui=legacy`. The original V4 is preserved byte-for-byte in `frontend/vendor/v4`; V5 is not the active base. [V4 integration and challenge assessment](docs/V4_INTEGRATION.md).

Without a key, QFIT shows explicitly labelled local source cards. To enable AI, copy `.env.example` to `.env`, set server-only `BLINKSPACE_ASSISTANT_PROVIDER=qfit` and `OPENAI_API_KEY`, then restart the launcher. Never include that file in Git or a release. The supplied OpenAI gpt-5.4-mini model is retained. Stop/retry, citations, and explicit action confirmation are included.

[Current 3D validation](reports/evolution-validation.json) · [Feature locations](docs/FEATURE_PARITY.md) · [Integration decisions](DECISIONS.md). The latest revision includes separate observation and published stellar-evolution timelines, corrected canvas proportions, spatial catalogue search, RedBeast branding and the QFIT robin with white chat text. These checks describe the preceding shell. Current V4 checks and their limits are recorded in reports/v4-validation.json. Earlier ZIP/Docker reports and the reviewed presentation describe historical revisions; see the dates in each report.

## Open the macOS release

Unzip the release, then double-click `Start-BlinkSpace.command`. It installs the pinned
Python dependencies on the first run, copies the bundled public presets into an empty
`data/` directory, and serves [BlinkSpace locally](http://127.0.0.1:8765). Keep the Terminal
window open. Python 3.12+ is required; Node is only needed when rebuilding the frontend.
The ZIP includes the compiled interface, local fonts and 25 real SPHEREx cutouts. An
internet connection is needed for the first dependency installation and new archive searches,
but ready presets do not require another archive download.

The new [stellar models](docs/STELLAR_MODELS.md) include source-labelled size, temperature,
clouds, coronal wind, accretion disks, jets and a schematic pulsation cycle. The on-screen
source notes include uncertainty, unknown values and target-specific limitations.


Each target also has a **Download Three.js model** link. The five reusable `.three.json`
models include geometry, materials, source notes and a shared animation module. See the
[model pack guide](frontend/public/models/README.md).

## Run locally

Use Python 3.12 or newer (the development environment uses 3.13) and Node.js 22.
From the project directory:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
export PYTHONPATH=backend
python docker/initialize_data.py seed-data data
# Without the bundled seed: python -m tools.prepare_presets && python -m tools.precompute_tracks
python -m uvicorn blinkspace.api:app_factory --factory --host 127.0.0.1 --port 8765 --workers 1
```

Open [the local application](http://localhost:8765). Preset preparation downloads real data
from IRSA; the time required depends on archive availability. Existing prepared sequences
are reused. The data directory is configurable with `BLINKSPACE_DATA_DIR`.

For interface development, run `npm run dev` from `frontend` in a separate terminal. Vite
proxies API requests to port 8765. Build output, catalogues and fonts are served locally;
there is no runtime CDN dependency.

## Containers and hosting

```bash
docker compose up --build
```

Open [the container application](http://localhost:8000). The named volume keeps observations
and downloaded data across restarts. A release image includes the five prepared presets;
its entrypoint copies them only into an empty data directory. For a build without archive
access, export the public preset seed first with `python -m tools.package_seed` from
`backend`. See [deployment instructions](docs/DEPLOY.md) for `$PORT`, health checks, seed
validation, proxy settings and hosting limits.

No public deployment or competition submission is claimed by this source package.
The current official Hugging Face documentation requires a paid account plan to create a
new Docker Space, even though CPU Basic has no hourly compute charge. Render's free web
services sleep and lose filesystem changes. Hosting conditions are recorded with official
source links in the deployment document; no paid service has been started.

## Validation and scientific reports

```bash
cd backend
../.venv/bin/python -m pytest -q
../.venv/bin/python -m pytest --live -q
cd ../frontend
npm test
npm run build
npm run lint
```

Ordinary backend tests use labelled synthetic fixtures. `--live` also contacts the real
archive. Current results and incomplete checks are recorded in `reports/` and `EVIDENCE.md`;
legacy screenshots and reports are not proof of the new 3D implementation.

Regenerate [the five target reports](reports/targets/OZET.md) from the prepared sequences:

```bash
cd backend
../.venv/bin/python -m tools.target_report
../.venv/bin/python -m tools.build_knowledge
```

Report dates, data releases, wavelength tolerances and limitations belong to each report.
No fresh motion significance or brightness ratio is asserted here without a new report.
**Independent user tests completed in this implementation: 0.** The protocol and blank
recording form are in [USER_TEST.md](docs/USER_TEST.md); developer checks are separate.

## Assistant and AI use

The distributed assistant is off by default; local source cards need no key. The `mock` provider
supports offline contract tests, and QFIT provides the optional real OpenAI connection. See
[the contract](docs/ASSISTANT_CONTRACT.md) and [AI usage disclosure](docs/AI_USAGE.md).

## License

Code: [MIT](LICENSE). Scientific catalogues, data and font licenses retain their original
attributions in [DATA_SOURCES.md](docs/DATA_SOURCES.md) and the bundled resource metadata.
