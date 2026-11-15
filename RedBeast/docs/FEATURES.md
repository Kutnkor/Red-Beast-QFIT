# Features and current validation

This document describes the 2026-11-14 integration. Old screenshots and old performance figures from the imported source are not acceptance evidence for this interface.

| Feature | Implementation and limitations |
|---|---|
| SPHERE-X v5 shell | Local typography, glass panels, target tabs, measurements, year ruler, Gaia color–magnitude diagram and original observation/analysis controls. `?ui=legacy` retained. Automated DOM checks pass; actual visual/mobile/GPU acceptance is pending. |
| Three stellar scenes | Persistent renderer; stellar surface/environment, 120 Gaia DR3 neighbours, real dated SPHEREx image planes. Unit-tested motion and WCS geometry; full visual/performance acceptance remains pending browser access. |
| Real catalogues | 120 nearby stars plus five targets; 8,785 real Hipparcos background stars. Effective temperatures retain their source or are null. |
| 2000–2100 motion | Cartesian linear space motion with measured RV; missing RV explicitly assumed zero. No parallax, observer effect or acceleration. |
| Stellar appearance | Source-backed radius and temperature, representative convection, clouds and accretion structures. Barnard: corona/wind; Epsilon Indi: separate Ba/Bb atmospheres and illustrative orbit; WISE: dark, cold cloudy surface; RW Aur: disk, dust and bipolar outflow; R Dra: compressed radius, a schematic radius/temperature cycle and outflow. See `STELLAR_MODELS.md` for sources and display assumptions. |
| SPHEREx views | Single, side-by-side, difference, stack and co-moving stack; invalid pixels remain transparent. A continuous A/B wavelength readout is shown. |
| Time stack | Depth represents the real observation date. Predicted tracks and measured centroids have distinct styles; missing measurements have explicit reasons. |
| Co-moving stack | Proper-motion shift and validity-weighted combination. Static sources smear. Display product only, never the input to photometry. |
| Analysis drawer | Frame metadata, layers, marks, light curve, spectrum and tasks retained. |
| Marks and sharing | Point/region marks, four classes, editable local drafts, read-only shared links and creator edit tokens. User notes are excluded from assistant context and release seed. |
| Search | Degrees/hours/sexagesimal RA/Dec, FOV, wavelength and date constraints; real job progress/cancel/retry. NASA archive outages return an error rather than fake results. |
| TR/EN and accessibility | Paired text keys, semantic controls, keyboard controls and data fallback for unavailable WebGL. Screen-reader and physical-device acceptance is not yet performed. |
| Assistant | QFIT robin, original Python agent and OpenAI gpt-5.4-mini adapter; same-origin SSE, source links, local non-AI cards, stop/retry, validated manual commands, context<=4KB and durable daily call budget. Off in the distributed package; private local activation uses `.env`. No key is included in source or ZIP. |
| Deployment | Docker uses a non-root user, configurable PORT, one process, healthcheck and a verified seed export. No public deployment has been made. |

Science limits include unresolved close binaries at the SPHEREx pixel scale, saturation, PSF differences, approximate proper-motion-only prediction and possible blending. The final scientific-confirmation field is always false. Current numerical results belong in regenerated `reports/targets/`, not in hard-coded interface copy.

Five-person user testing, full desktop/mobile browser acceptance, rendering FPS/resource stability, a public HTTPS link and competition submission remain separate acceptance tasks. See `EVIDENCE.md` and `STATUS.md` for current results.
