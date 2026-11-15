# BlinkSpace — Find what changes in the sky

## High-level summary

BlinkSpace is a web tool that lets anyone type a sky position (Right Ascension and Declination) — or pick a ready
target — and watch real SPHEREx images of that patch of sky taken at different times, like a short video. Moving
objects shift between frames and variable objects change brightness. Users can blink, compare side by side,
subtract or stack frames, overlay Gaia and WISE catalogue positions, read a light curve or a spectrum, mark what
they notice and share it with a link. No account is needed, and the interface is in Turkish and English.

What makes it more than an image player is that it only compares what is physically comparable. In SPHEREx every
detector pixel sees a different wavelength, so the same star is observed at a different wavelength in almost every
exposure. BlinkSpace selects, for the requested position, the exposures in which the wavelength *at that position*
is the same (within half a bandwidth), aligns them on the sky without pinning any source, keeps bad pixels as "no
measurement" instead of black, and shows every date, wavelength, quality flag and source link.

## Feature overview

| Need | BlinkSpace |
|---|---|
| Public-facing web tool that shows SPHEREx images changing over time | single-page web app + API; frames placed on a timeline at their real observation dates |
| Users enter RA and Dec | degrees, hours or sexagesimal, explicit unit choice, server-side validation |
| Series of images like a little video | play/pause, step, speed, A/B blink, synchronised side-by-side |
| Reference targets: Barnard's Star, Epsilon Indi B, WISE 0855, RW Aurigae, R Draconis | all five are one-click presets with a written test report each |
| Easy to update with new data releases | products are found by live archive query; the newest reprocessing of each exposure is chosen automatically; layers and flags are read by name |
| Use the 102 bands; spectra on the fly | wavelength-group switcher; spectrum of any position from all exposures in a time window |
| Add or subtract images | difference and stack views, with their caveats shown |
| Choice of field of view | 2–30 arcminutes |
| Overlay Gaia / WISE | Gaia DR3 (propagated by proper motion) and AllWISE catalogue layers |
| Coordinates in the URL | `/?ra=…&dec=…&fov=…`, `/?target=…`, `&embed=1` |
| Metadata such as contamination flags | per-frame flags, quality layer, invalid/suspect/comparable fractions, provenance dialog |

## What we found with real data

All numbers below come from SPHEREx images queried from IRSA on 2026-11-14 (reports in `reports/targets/`).

- **Barnard's Star** — 6 matched frames at 1.51 µm over 393 days. The star saturates the detector, so its core is
  shown as "no measurement"; the centre of that core still moves north by 2.0 pixels. A linear fit gives
  (−5.2, +10.4) ± 1.7 ″/yr against the catalogue (−0.8, +10.4) ″/yr: motion seen at 5.0σ, consistent with the catalogue.
- **Epsilon Indi B** — unsaturated, detected at S/N ≈ 190 at 1.58 µm at the predicted positions. Fit
  (+3.9, −3.0) ± 0.5 ″/yr against the catalogue (+4.0, −2.5): motion seen at 7.0σ over 1.4 years (1.15 pixels).
  Its on-the-fly spectrum shows the J and H peaks and the deep absorption between them expected for a T dwarf.
- **RW Aurigae** — saturated or flagged longward of 0.85 µm, clean at 0.76 µm. Aperture flux rises 74 → 124 → 192 mJy
  between September 2025 and September 2026 (2.6×, 5.6σ) while five comparison stars in the same frames stay
  constant to a few percent.
- **R Draconis** — in the SPHEREx deep field (hundreds of exposures), but its core is saturated in every frame:
  the tool reports that brightness cannot be measured rather than inventing a light curve.
- **WISE 0855−0714** — not detected in any single frame at 4.86 µm, and the predicted path passes 4.5″ from a
  G = 16.3 background star (inside one 6.15″ pixel). The same positions show flux at 2.34 µm, where the brown dwarf
  should be invisible, so the weak signal is contamination. Reported as "not detected".

None of these is presented as a discovery or as a scientific confirmation; the tool separates "data available",
"source detected", "change seen" and "scientifically confirmed", and never sets the last one.

## How it works

1. Validate the coordinates. 2. Query IRSA (TAP) for every Level-2 spectral image covering the position; drop
reprocessed duplicates. 3. Predict the wavelength at the position in each exposure from its footprint and group
exposures by wavelength. 4. Download small cutouts of the chosen frames and store them unmodified with their SHA-256.
5. Read image, flags, variance and wavelength layers by name. 6. Re-check the wavelength, classify flags, resample to
a common north-up grid at the native 6.15″ scale. 7. Subtract a recorded background, apply one display scale to all
frames. 8. Check the alignment against Gaia DR3 stars (0.4–1.3″ rms on four of the five targets). 9. Store the
sequence; a shared link always reopens exactly this sequence even if the archive changes later (it did change, from
QR2 to DR1, between two of our working days).

Long work runs in a job queue independent of the web request, with real stages, cancel, retries and time-outs.

**Stack:** Python (astropy, reproject, photutils, NumPy, SciPy), FastAPI, SQLite; React + TypeScript (no UI
framework, no external requests). Historical baseline (not current acceptance): 131 backend tests on synthetic data, 4 tests against the live archive, 87
frontend tests.

## Data and resources

- SPHEREx Level-2 spectral images, NASA/JPL-Caltech, served by the NASA/IPAC Infrared Science Archive (IRSA): TAP
  and image cutout services. SPHEREx Team (2025), doi:10.26131/IRSA629.
- Gaia DR3 (ESA/DPAC) and AllWISE catalogues via IRSA; SIMBAD (CDS) for target identities and proper motions.
- IRSA SPHEREx archive documentation and tutorials; astropy and reproject documentation.

Full list with versions and licences: `docs/DATA_SOURCES.md`. BlinkSpace is an independent project and is not
developed or endorsed by NASA.

## Limitations (short)

6.15″ pixels blend close sources; bright stars saturate; calibration is early-release; difference images are not
PSF-matched; candidate suggestions are a review aid validated only on synthetic injections; no test with real users
yet; not yet deployed publicly. Details: `docs/METHOD.md`, `docs/FEATURES.md`.

## Use of AI tools

See `docs/AI_USAGE.md`.
