# Data sources, licences and attributions

Access dates: 2026-11-14 and 2026-11-14 (all services queried live on those days).

## Data

| Source | What we use | How | Notes |
|---|---|---|---|
| **SPHEREx Level-2 spectral images** (NASA/JPL-Caltech; served by IRSA) | IMAGE, FLAGS, VARIANCE, ZODI, WCS-WAVE layers of cutouts | TAP `https://irsa.ipac.caltech.edu/TAP` (`spherex.plane`, `spherex.artifact`); IBE cutouts `https://irsa.ipac.caltech.edu/ibe/data/spherex/...?center=&size=` | On 2026-11-14 the query returned collections `spherex_qr2`, `spherex_qr2_deep`, `spherex_qr3_deep` (pipeline 6.4–7.0.5). On 2026-11-14 it returned `spherex_dr1`, `spherex_dr1_deep`, `spherex_qr3`, `spherex_qr3_deep` (all pipeline 7.0.5). The app reads the release from each product's path and keeps the newest copy. |
| Gaia DR3 (ESA/DPAC) | positions, proper motions, G magnitudes | IRSA TAP table `gaia_dr3_source` | alignment check, comparison stars, catalogue layer |
| AllWISE Source Catalog (NASA/JPL-Caltech/UCLA) | positions, W1/W2 | IRSA TAP table `allwise_p3as_psd` | catalogue layer, blending check |
| SIMBAD (CDS, Strasbourg) | identities, J2000 positions, proper motions, parallaxes of the five targets | TAP at the CfA mirror `https://simbad.harvard.edu/simbad/sim-tap` (the Strasbourg endpoint returned 404 on 2026-11-14) | stored in `backend/blinkspace/resources/targets.json` with bibcodes |

### Citations and acknowledgements

- SPHEREx Team (2025), *SPHEREx Quick Release Spectral Images*, IRSA, doi:10.26131/IRSA629. **Open item:** the
  citation/DOI for the DR1 collection that appeared on 2026-11-14 could not be verified from the documentation
  pages we read; check the IRSA SPHEREx page before publishing.
- This work makes use of the NASA/IPAC Infrared Science Archive, which is funded by NASA and operated by the
  California Institute of Technology.
- This work has made use of data from the European Space Agency (ESA) mission Gaia
  (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis Consortium (DPAC).
- This publication makes use of data products from the Wide-field Infrared Survey Explorer, a joint project of the
  University of California, Los Angeles, and the Jet Propulsion Laboratory/California Institute of Technology,
  funded by NASA.
- This research has made use of the SIMBAD database, operated at CDS, Strasbourg, France.
- Coordinate sources per target (bibcodes from SIMBAD): Gaia DR3 `2020yCat.1350....0G` (Barnard's Star, Eps Indi B,
  R Dra); Kirkpatrick et al. `2021ApJS..253....7K` (WISE 0855−0714); van Leeuwen `2007A&A...474..653V` (RW Aur).

NASA data are used as published. **BlinkSpace is an independent project; it is not developed, endorsed or
sponsored by NASA, JPL, Caltech/IPAC or ESA.**

## Documentation consulted

- IRSA SPHEREx archive documentation: data access, data products (read 2026-11-14).
- IRSA tutorials (content licence BSD-3-Clause): *SPHEREx cutouts*, *SPHEREx source discovery tool demo*.
  **Adapted ideas, no code copied:** the `plane ⨝ artifact` footprint query, appending `?center=&size=` to the
  artifact URI, and evaluating the "W" alternate WCS with SIP disabled; the list of flags treated as bad for
  photometry. The tutorial's QR2-era HDU order and file paths were *not* reused; both were re-verified on current files.
- astropy coordinates/WCS and `reproject` documentation.

## Software

| Package | Version | Licence |
|---|---|---|
| astropy | 8.0.2 | BSD-3-Clause |
| numpy | 2.5.4 | BSD-3-Clause |
| scipy | 1.18.1 | BSD-3-Clause |
| reproject | 0.21.0 | BSD-3-Clause |
| photutils | 3.1.1 | BSD-3-Clause |
| FastAPI | 0.162.4 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| pydantic | 2.14.3 | MIT |
| Pillow | 13.0.0 | MIT-CMU |
| psutil | 7.2.2 | BSD-3-Clause |
| pytest (dev) | 9.2.0 | MIT |
| React, React DOM | 19.3.1 | MIT |
| Vite | 8.3.8 | MIT |
| TypeScript (dev) | 7.0.2 | Apache-2.0 |
| vitest, Testing Library, jsdom, oxlint (dev) | 5.1.0 / 16.3.3 / 31.0.0 / 1.93.0 | MIT |

Exact pins: `backend/requirements.txt`, `backend/requirements.lock`, `frontend/package-lock.json`.
BlinkSpace itself is released under the MIT licence (`LICENSE`).

## Use of AI tools

The code, tests and documentation in this repository were produced with Claude (Anthropic)
driven by a written specification. See `docs/AI_USAGE.md`.
