# Data sources and retrieval mechanisms

Everything Q-FIT returns comes from one of the services below. This file states exactly which
request is sent, how the answer is mapped, and what has been verified.

## 1. NASA/IPAC IRSA: SPHEREx archive

Base: `SPHEREX_BASE_URL` (default `https://irsa.ipac.caltech.edu`). Code:
`app/astronomy/archive_client.py`, `app/astronomy/spherex_client.py`.

### Releases and collections (IRSA, November 2026)

| SIA2 collection | Content |
|---|---|
| `spherex_dr1` | DR1 Spectral Image MEFs, wide survey |
| `spherex_dr1_deep` | DR1 Spectral Image MEFs, deep survey |
| `spherex_qr3` | QR3 Spectral Image MEFs, wide survey |
| `spherex_qr3_deep` | QR3 Spectral Image MEFs, deep survey |
| `spherex_dr1_cube` | DR1 All-Sky Cube tiles |

DR1 (reprocessed QR2 data) and QR3 are meant to be used together. QR2 is no longer searchable
through SIA2. Calibration products are only in the browsable directories and are not used by Q-FIT.

### Products

- **Spectral Image MEF** (level 2): one file per detector per exposure, about 60–70 MB, 2040×2040,
  extensions `IMAGE` (MJy/sr, zodiacal light not subtracted), `FLAGS`, `VARIANCE`, `ZODI`, `EPSF`,
  `WCS-WAVE`. Six detectors cover 0.75–5.0 µm; within one image the wavelength changes with pixel
  position. Not every observation has all six detectors.
- **All-Sky Cube** (DR1): HEALPix order-5 tiles, 512×512 pixels × 102 channels, zodiacal light
  subtracted, about 300 MB per tile. IRSA documents channels 51 and 52 as empty.

Q-FIT therefore never treats a spectral image as a 102-band spectrum. Only cube tiles are reported
with `spectral_channels: 102`.

### 1a. Observation search: SIA 2.0

```
GET {base}/SIA?COLLECTION=spherex_dr1&COLLECTION=spherex_dr1_deep&COLLECTION=spherex_qr3
              &COLLECTION=spherex_qr3_deep&POS=circle {ra} {dec} {radius}
              [&TIME={mjd_lo} {mjd_hi}][&BAND={m_lo} {m_hi}]&RESPONSEFORMAT=CSV&MAXREC={n}
```

The archive returns ObsCore rows for every image whose footprint intersects the circle. Mapping:

| ObsCore column | Q-FIT field | Conversion |
|---|---|---|
| `obs_publisher_did` (`ivo://irsa.ipac/{collection}?{obs_id}/{product}`) | `observation_id` | → `collection:obs_id:product` |
| `obs_id`, `obs_collection` | `obs_id`, `collection` | none |
| `energy_bandpassname` (`SPHEREx-D4`) | `bandpass`, `detector` | trailing digit |
| `t_min`, `t_max` (MJD) | `t_*_mjd`, `t_*_utc` | MJD → UTC ISO-8601 |
| `em_min`, `em_max` (m) | `wavelength_*_um` | × 10⁶ |
| `em_res_power`, `t_exptime`, `s_fov`, `s_pixel_scale` | same meaning | none |
| `s_ra`, `s_dec` | `center_ra`, `center_dec` | none (image centre) |
| `access_url`, `access_format`, `access_estsize` | same | copied verbatim |
| `cloud_access` | `cloud_access` | JSON (AWS bucket `nasa-irsa-spherex`, key, region) |
| `s_region` | `footprint` | only with `include_footprint` |

Rows without `access_url` are dropped. Duplicates are removed by `observation_id`. Availability is
`true` only if at least one row survives.

### 1b. Observation metadata by id: TAP

```
GET {base}/TAP/sync?FORMAT=csv&QUERY=
  SELECT p.obs_publisher_did, p.productid, p.calibrationlevel, p.dataproducttype,
         p.energy_bounds_lower, p.energy_bounds_upper, p.energy_resolvingpower, p.energy_bandpassname,
         p.time_bounds_lower, p.time_bounds_upper, p.time_exposure, p.position_samplesize,
         p.provenance_name, p.provenance_version, p.datarelease, p.pt,
         a.uri, a.contenttype, a.contentlength, a.contentchecksum
  FROM spherex.plane p JOIN spherex.artifact a ON a.planeid = p.planeid
  WHERE p.obs_publisher_did = 'ivo://irsa.ipac/{collection}?{obs_id}/{product}'
```

The download URL is `{base}/{a.uri}`, the construction IRSA's own cutout tutorial uses. Lookup
order: (1) products seen in a recent search (in-memory, no request), (2) an SIA2 search at the
optional position hint, (3) the TAP query above. Ids are validated against a strict pattern before
they are placed in ADQL.

### 1c. Images and cutouts: IBE

Full files: the `access_url` from the archive. Cutouts: `{access_url}?center={ra},{dec}&size={deg}`,
the syntax IRSA documents for Spectral Image MEFs on its own servers. With `verify=true` Q-FIT sends
`HEAD` (falling back to a one-byte range `GET`) and reports the outcome in `download_check`. Without
it, `download_check.verified` is `null`: reference returned, download not attempted.

### 1d. Spectral data

1. Cube tile: SIA2 with `COLLECTION=spherex_dr1_cube` at the target.
2. Band coverage: the spectral-image rows grouped by detector.
3. Optional samples (`extract_samples`): for up to 12 exposures Q-FIT downloads a 0.01° cutout
   (size-capped), finds the target pixel with the image WCS, reads `IMAGE`, `VARIANCE`, `ZODI`,
   `FLAGS` there, and evaluates the spectral WCS (`key="W"`, SIP disabled) for wavelength and
   bandwidth, as in IRSA's "Introduction to SPHEREx Spectral Images" notebook.

### 1e. Observation periods

All spectral-image rows at the position are sorted by `t_min` and split wherever the gap exceeds
`gap_days` (default 20). No motion or variability analysis is done.

## 2. SIMBAD (CDS Strasbourg)

Code: `app/astronomy/object_resolver.py`, through `astroquery.simbad` (SIMBAD TAP).

- Name: `Simbad.query_object(name)`, then `"NAME " + name` for common names. Fields: `main_id`,
  `ra`, `dec` (ICRS degrees), `otype`, `coo_bibcode`, `matched_id`.
- More than one distinct `main_id` → `ambiguous`, with candidates. Q-FIT does not pick one.
- No exact match → CDS Sesame → partial-name ADQL on `ident` (`id LIKE 'NAME %…%'`) → JPL Horizons.
- Cone search: `Simbad.query_region(coord, radius, criteria="otype = '<code>..'")`.

## 3. CDS Sesame

Fallback only, through `astropy.coordinates.name_resolve.get_icrs_coordinates`. Returns coordinates
without an object type; such objects are labelled `catalog_source: "CDS Sesame"`.

## 4. JPL Horizons

Code: `app/astronomy/horizons_client.py`. SIMBAD is not a Solar System catalog, so names that are
planets, major moons, well-known small bodies, or comet/provisional designations go here.

```
GET https://ssd.jpl.nasa.gov/api/horizons.api?format=text&COMMAND='{id}'&EPHEM_TYPE=OBSERVER
    &CENTER='500@399'&TLIST='{JD}'&QUANTITIES='1'&ANG_FORMAT=DEG&CSV_FORMAT=YES
```

Quantity 1 is astrometric RA/Dec (ICRF). `COMMAND`: planets by id (`499`), numbered comets by
designation (`3I`), provisional designations as `DES=C/2025 N1;CAP;NOFRAG`, other small bodies as
`name;`. The position is geocentric at one epoch (`epoch_utc`, default now). SPHEREx is in low Earth
orbit, so the parallax difference matters only for very close bodies.

Names of the form `<number> <name>` are not sent to Horizons automatically, because stars such as
"51 Pegasi" look the same; they reach Horizons only after SIMBAD and Sesame fail, and the returned
body name must match.

## 5. Catalog versus mission data

`object` and `data.catalog` hold catalog data. `data.observations`, `image_products`,
`spectral_products` and `observation_periods` hold SPHEREx archive data. A catalog hit never sets
`spherex_available`; only an archive response does.

## 6. Verification status (2026-11-14)

The build environment could not open connections to the astronomy hosts from Python (outbound
network policy), so Q-FIT's own live test-suite has **not** been executed yet. What was checked
instead, by requesting the real endpoints directly while building:

| Item | Status |
|---|---|
| SIA2 query form, `RESPONSEFORMAT=CSV`, repeated `COLLECTION`, `MAXREC` | Verified against IRSA; column names and value formats in the mapping table come from those responses |
| `spherex_dr1_cube` collection returns the covering tile | Verified against IRSA |
| `spherex.plane` / `spherex.artifact` columns used in the TAP query | Verified against IRSA (`SELECT TOP 1 *`) |
| Horizons request and ephemeris line format (`499`, `3I`) | Verified against JPL |
| The TAP join with the `obs_publisher_did` filter | Not run live |
| Cutout download and spectral-WCS sample extraction | Not run live |
| SIMBAD and Sesame calls | Not run live |
| Gemini calls | Not run live (no API key) |

Run `pytest --run-live -rs` and `python scripts/live_check.py` on a machine with normal internet
access to close the open items.

## 7. References

- SPHEREx at IRSA: https://irsa.ipac.caltech.edu/Missions/spherex.html
- SPHEREx Archive User Guide: https://caltech-ipac.github.io/spherex-archive-documentation/
- IRSA SIA: https://irsa.ipac.caltech.edu/ibe/sia.html
- IRSA SPHEREx tutorials: https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/
- SPHEREx DR1 Spectral Images, DOI 10.26131/IRSA678; All-Sky Cube, DOI 10.26131/IRSA679
- SIMBAD: https://simbad.cds.unistra.fr/simbad/
- JPL Horizons: https://ssd.jpl.nasa.gov/horizons/
