# Scientific backend implementation evidence

Work recorded by OpenAI Codex. This report distinguishes tested local behavior from live archive downloads.

## Local validation completed

- Installed exact existing Python 3.13 dependency pins in project `.venv` (root agent performed network install). No scientific dependency versions were changed.
- Original backend test suite passed: 152 collected, four opt-in live tests skipped.
- Independent `tools.build_motion_golden` uses Astropy 8.0.2 `SkyCoord.cartesian` plus `velocity * delta Julian years`; it does **not** call `apply_space_motion` and does not import frontend calculations. Twenty target/year positions are saved at `frontend/src/tests/golden/motion.json`.
- Barnard 2050 reproduced within 1e-12 pc of `[-0.017739342162699453, -1.8178101926870318, 0.15385109849645198]`. Three coordinates follow the plan's explicit `[ICRS x, ICRS z, ICRS y]` mapping.
- New FakeArchive integration tests passed for precomputed vs predicted-only tracks, stronger moving-source peak in the co-moving mean, static-star vertical variance increasing by more than 25%, missing-target HTTP 422, and an off-grid target returning no measurement.
- Existing backend suite plus these four integration tests passed together. Resource build tests are separately pending successful live-source downloads at this checkpoint.

## Implemented interfaces

- `/api/motion`, `/api/sky/bright.json`, `/api/sky/bright.bin`: prepared resources with `Cache-Control: public, max-age=86400`; missing preparation is explicitly HTTP 503.
- `/api/sequences/{id}/track`: uses sequence-fingerprint-matched precomputed track, otherwise `predicted_only` or `none`; never measures on request or marks a prediction as a detection.
- `tools.precompute_tracks`: measures prepared presets using the existing native-pixel measurement pipeline, preserves its status ladder, and records measured positions only when the original detection rule is met. It writes both `track.json` and auditable `target_measurement.json` atomically.
- `/api/sequences/{id}/track_stack`: background-subtracted, wavelength-comparable valid pixels shifted with bilinear interpolation to reference frame 0. A shifted validity weight must exceed 0.999; each output pixel requires ceil(n/2) valid input frames. Invalid output remains NaN. PNG output is a display product; no detection count or new photometry is asserted.
- Off-grid native measurements now include an explicit invalid-photometry record, fixing a pre-existing missing-key crash without altering detection thresholds.
- Assistant router integration preserves HTTP exception headers, including Retry-After.

## Data provenance decisions

- Original 120 Gaia rows and five target astrometric rows are retained unmodified numerically. Canonical snake_case aliases are added. Missing radial velocity is null in the canonical field, with the original value and availability flag retained for audit.
- The four non-Gaia original target `colorIndex=3` fields were illustrative; they are **not** used as BP−RP measurements or to infer Teff. Canonical `bp_rp` is null for these targets, and the original value is retained with an explanatory note.
- The mean-dwarf calibration is not applied to the young RW Aur or evolved Mira R Dra system; absent a defensible individual measurement they remain Teff unknown.
- Epsilon Indi B is unresolved: no single system Teff is invented. Component display midpoints 1320 K and 910 K are explicitly accompanied by their published ranges 1300–1340 K and 880–940 K and [King et al. 2010](https://doi.org/10.1051/0004-6361/200912981).
- WISE 0855 display estimate 250 K is labeled approximate, range 225–260 K, with [Luhman 2014](https://doi.org/10.1088/2041-8205/786/2/L18).
- Reference values are parsed by the builder from primary-source text, not silently guessed. NASA lists **1896 arcsec** as the Moon's mean apparent diameter at opposition from Earth's equator ([Moon Fact Sheet](https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html)); it is not a constant actual observed lunar diameter. J2000 mean obliquity is the IAU 2006 coefficient 84381.406 arcsec from ERFA/SOFA `obl06`.
- Mamajek source is the author's `EEM_dwarf_UBVIJHK_colors_Teff.txt`, version 2022.04.16. It is cached with URL, fetch time, bytes and SHA-256. The same metadata is kept for TAP schemas and responses.
- Hipparcos is ESA partner data. The builder requires verified column names and actual V<6.5 rows before producing its binary; it does not generate filler stars.

## Live archive status at initial checkpoint

- IRSA Gaia schema query succeeded and confirmed `source_id` and `teff_gspphot`.
- The 120-source Teff query returned upstream HTTP 502; the first SPHEREx preset spatial query also returned 502 after the existing three bounded attempts. The first CDS VizieR connection timed out. These are not successful data downloads and no scientific result is claimed from them.
- `reports/motion-build.log`, `reports/presets-build.log`, and `reports/sky-build.log` contain the actual build output. A read-only `tools.probe_archive` diagnostic compares equivalent GET/POST TAP requests before any transport change.
- Resource checks and live preparation will be recorded below when completed.

## Completed source downloads and offline rebuild

- IRSA's ordinary table queries failed even for `SELECT TOP 1`, for GET and POST. The read-only diagnostic is saved in `reports/tap-probe.log`; this was an upstream access problem, not evidence that a scientific query returned no rows.
- The equivalent primary ESA Gaia DR3 service succeeded after verifying its `gaiadr3.gaia_source` schema. The 120-ID temperature response is 3,016 bytes, SHA-256 `1600f9e810958719166fcdbfa3b501b1f2db0e838b450c9d597d52b17fde3ad4`.
- Across 120 neighboring stars plus five targets: 58 entries have Gaia GSP-Phot temperatures, 58 have explicitly approximate Mamajek BP−RP temperatures, one has the cited WISE 0855 literature estimate, and eight remain unknown. These totals include the separately presented Barnard target.
- Mamajek table: 55,680 bytes, SHA-256 `1de2edeec17bb3346e0e4e70b999de5ee29947df38474e64cddb7cfacc164b7f`.
- Strasbourg VizieR TAP connections timed out. The official Harvard VizieR ASU mirror succeeded with schema/column metadata checked before fetching the table. Its actual Hipparcos V<6.5 TSV is 564,651 bytes, SHA-256 `5764ac7ba0cd722ecd68162dae002d17c1396fb347825bb10c638c65106aa547`.
- Bright sky: **8,785 real Hipparcos objects**, 245,980 bytes (8,785 × 7 Float32), SHA-256 `734548d346b4282d670ec61f85f3d8f1bbb0f9290b7a8011ad18733aea787a58`. No artificial background objects were inserted.
- Both builders were re-run successfully in the child process with networking unavailable, using checksum-matched cached responses; the binary checksum was unchanged. The independent 20-position Astropy golden was also regenerated successfully.

Reproduction commands (from project root):

```sh
PYTHONPATH=backend .venv/bin/python -m tools.build_motion_catalogue --input backend/blinkspace/resources/source_data/input_catalogue.json --gaia-tap-url https://gea.esac.esa.int/tap-server/tap/sync --gaia-table gaiadr3.gaia_source
PYTHONPATH=backend .venv/bin/python -m tools.build_bright_sky --asu-url https://vizier.cfa.harvard.edu/viz-bin/asu-tsv
PYTHONPATH=backend .venv/bin/python -m tools.build_motion_golden
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests
```

## Runtime robustness and final local test checkpoint

- Full backend suite: **168 passed, 4 opt-in live tests skipped** (172 collected). This includes all resource equality/provenance/binary/golden tests, all track/co-moving integration tests, and four synthetic-HTTP SIA tests. No live test is represented as passed merely because its local equivalent passed.
- IRSA's documented live SIA2 service is supported as a fallback after TAP errors, or explicitly with `BLINKSPACE_ARCHIVE_PROTOCOL=sia`. It queries DR1 and QR3, wide and deep collections; all four must succeed before reporting full discovery. Each response URL and SHA-256 is saved in sequence provenance. Fields SIA does not supply (archive MD5, software version) are left unknown at discovery; actual FITS VERSION and locally calculated raw SHA-256 are recorded during processing.
- The root's first successful live SIA response contained 239 rows; 238 were valid Level-2 spectral images. Its response is `reports/sia-probe.xml`. This validates parsing a real response, separately from the mocked protocol tests.
- Controlled root HTTP probes showed IRSA's proxy rejecting `+` separators in SIA geometry in a request that succeeded with `%20`. SIA URL construction now percent-encodes geometry spaces without altering coordinates; the protocol tests pass after this change.
- `BLINKSPACE_GAIA_PROVIDER=esa` selects the equivalent primary Gaia DR3 table for alignment/comparison stars and records its provider URL. Pipeline version is now **1.2.0**, producing a new cache key without deleting older sequences.
- Scientific JSON writes are atomic and mode 0644 so a non-root container can read public resources. The API header middleware now uses pure ASGI response-start edits, preserving file streaming and original server exceptions. Docker validation is recorded separately by the deployment agent.
- `backend/requirements.lock` was regenerated from the validated Python 3.13 environment; Docker uses it as constraints so runtime indirect versions match the local test environment.
