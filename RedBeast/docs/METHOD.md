# Scientific method and limitations

BlinkSpace shows real SPHEREx Level-2 spectral images of one sky position at different times, and nothing else.
This document states exactly what the pipeline does to the data, why, and where it stops being trustworthy.
Every rule below is enforced by a test in `backend/tests` (file names in brackets).

## 1. What a SPHEREx "image at a wavelength" is

Each SPHEREx detector sits behind a linear variable filter: the central wavelength changes continuously across the
detector. A star is therefore observed at a different wavelength in every exposure, depending on where it lands.
**The same detector does not mean the same wavelength** [`test_science.py::test_same_detector_does_not_mean_same_wavelength`].

Consequences for a time comparison:

- Two frames may be compared in time only if the wavelength *at the target* is the same. BlinkSpace requires
  `|λ − λ_ref| ≤ tol × Δλ`, with Δλ the bandwidth (FWHM) at λ_ref. Default `tol = 0.5` (centres at most half a
  resolution element apart: adequate for visual inspection). Quantitative brightness comparison uses `tol = 0.25`;
  if fewer than two/three points satisfy it, the 0.5 set is used with an added 10% systematic for the spectral
  slope, and this is stated in the result.
- The match at the centre does not hold across the field: the wavelength gradient is about one resolution element
  per ~180 detector pixels. A per-pixel wavelength map is computed for every frame, and pixels outside the tolerance
  are masked as "not comparable" (blue layer in the viewer) [`test_wavelength_map_and_comparable_mask`].
- Frames at other wavelengths are offered separately as "wavelength exploration" and as a spectrum; they are never
  placed in a time sequence.

Wavelengths come from the `WCS-WAVE` lookup table inside each file (bilinear interpolation, ~1 nm accuracy per the
archive documentation). Our evaluation is checked against astropy's `-TAB` implementation on real files (identical
to 1e-9 µm) [`test_live_archive.py`]. The SIP distortion must not be applied to the alternate "A"/"W" coordinate
systems; astropy applies it by default, which shifted detector coordinates by ~24 pixels in our first reading.

## 2. Finding and selecting observations

- One TAP query (`spherex.plane ⨝ spherex.artifact`, `CONTAINS(POINT, poly)`) returns every Level-2 image whose
  footprint contains the position. Times are UTC (MJD).
- A record is one exposure × one detector. Reprocessed copies of the same (observation id, detector) are **one**
  observation: the newest release/L2 version/processing date is kept. Different detectors stay separate
  [`test_reprocessed_copies_are_one_observation_and_detectors_stay_separate`].
- Before downloading, the target's detector pixel is estimated from the four footprint corners (measured accuracy on
  real files: 3–8 pixels) and its wavelength from a per-detector `WCS-WAVE` table. Exposures with the target too
  close to the detector edge for the requested field are dropped.
- Candidates are grouped by wavelength; the default group is the one with the most separate visits, then the longest
  time span. Up to N frames are chosen, one per visit first, keeping the first and last visit.
- After download the wavelength is recomputed from the file itself and the tolerance re-applied; a frame that fails
  is rejected and listed.

## 3. Reading the files

HDUs are read **by name**. Verified on real files: QR2 (pipeline 6.4, 6.5.x) has `PSF` as the fifth HDU, pipeline
7.0.x has `EPSF`. Flag definitions are read from each file's `FLAGS` header (`MP_<NAME>` in 6.x, `MSKNnnnn` in 7.x);
no fixed bit table is assumed [`test_reads_both_release_layouts_by_name`, `test_flag_definitions_come_from_each_file_header`].

Flag classes:

| Class | Flags | Treatment |
|---|---|---|
| invalid | NONFUNC, MISSING_DATA, SUR_ERROR, HOT, COLD, PHANTOM, REFERENCE, non-finite values | no measurement: NaN, transparent in previews, never zero |
| suspect | TRANSIENT, OVERFLOW, NONLINEAR, PERSIST, OUTLIER, PHANMISS, DICHROIC, FULLSAMPLE, CROSSTALK, GHOST*, STREAK, BLOOM, SNOWBALL, HALO, and any unknown new name | value shown, mask carried separately |
| info | SOURCE | no mask |

## 4. Alignment

All frames are resampled (bilinear, `reproject`) onto one grid: tangent projection centred on the requested ICRS
position, north up, east left, native 6.15″ pixels, odd size. Alignment uses only each file's own WCS (TAN-SIP).
**No source is pinned between frames**, so real motion survives [`test_controlled_shift_is_measured_and_moving_source_is_not_pinned`].

- Invalid pixels are set to NaN before resampling; the invalid mask is resampled as a float and any output pixel it
  touches is invalid (conservative growth). Suspect masks are carried by nearest neighbour. Flag bits are never
  interpolated [`test_invalid_pixels_stay_missing_not_zero_and_flags_are_not_averaged`].
- Coverage outside a frame's footprint is invalid; frames covering < 60% of the grid are rejected.
- **Check:** for every sequence, Gaia DR3 stars (G ≤ 15.5, isolated, clean) are propagated to each frame epoch and
  their centroids measured in the aligned frame. Residual rms on the five targets: 0.4–1.3″ (0.06–0.2 pixel), except
  R Dra where stars inside the saturated star's halo dominate (reported as measured).

## 5. Background and display

Per frame, a sigma-clipped median of valid, unflagged, non-source pixels is subtracted (constant; value and scatter
recorded per frame; the archive's ZODI model median is recorded too but not used). All frames of a sequence share one
asinh stretch and one black/white pair. Previews are 8-bit PNGs with transparent invalid pixels and are **never** used
for measurement.

## 6. Measurements

- **Position:** flux-weighted centroid in a 5×5 box on the aligned frame. Per-point error = the sequence's own Gaia
  residual rms (floor 0.1 pixel). For a saturated star the centroid of the invalid core is used with an assumed
  0.3-pixel error.
- **Motion:** linear fit of position against time; compared with the catalogue proper motion. Parallax and
  spacecraft position are not modelled (≤ 0.55″ for these targets, < 0.1 pixel). The predicted-position overlay is
  proper-motion-only and labelled so.
- **Brightness:** aperture photometry (r = 2 pixels, annulus 4–7) on the **native, un-resampled** cutout with the
  VARIANCE layer. Any invalid pixel in the aperture → no measurement. OVERFLOW/NONLINEAR in the aperture → value
  kept but marked unreliable. No aperture correction: only relative changes at one wavelength are meaningful.
  Comparison stars (Gaia, same frames, same aperture) give a per-frame scale and a systematic scatter that is added
  to the errors.
- **"Change seen"** = ≥ 3σ in our own measurement (brightness additionally ≥ 20% and normalised by comparison
  stars). It is never reported as scientifically confirmed.

## 7. Advanced products and their limits

| Product | What it is | Limits |
|---|---|---|
| Difference | B − A of background-subtracted, wavelength-comparable valid pixels | no PSF matching; undersampled PSF leaves residuals on static stars; PSF FWHM differs between releases (5.3″ vs 7.5″) |
| Stack | mean of valid comparable pixels, ≥ max(2, n/2) frames per pixel | moving sources blur (expected motion in pixels is shown); variable sources are averaged |
| Gaia / AllWISE layers | **catalogue** positions (not images) | Gaia epoch 2016.0, propagated by proper motion; AllWISE ≈ 2010.5, not propagated; resolutions differ |
| Light curve | aperture flux vs real date for one wavelength group | see Brightness above |
| Spectrum | aperture flux vs wavelength from all exposures in a time window | **not simultaneous**; each point carries its date; blended neighbours within 12″ |
| Candidate suggestions | ≥ 6σ regions of the difference image whose 5×5 box flux changes by ≥ 25%; ± pair within 4 px = possible motion; touching flagged pixels = possible artefact | review aid only; validated on synthetic injections (labelled as such in the tests), not a detection pipeline |

## 8. Known limitations

- Pixel scale 6.15″ and an undersampled PSF: close pairs (Eps Indi Ba/Bb, RW Aur A/B) are one source; background
  stars within ~12″ contaminate photometry (this is what prevents a clean WISE 0855 measurement).
- Bright stars saturate: Barnard's Star, R Dra and RW Aur longward of ~0.85 µm have invalid or unreliable cores.
- Quick-release / first-release calibration; aperture fluxes are not absolute.
- The Gaia query for the alignment check adds 30–85 s for a new position.
- No shift-and-stack along a predicted motion, no PSF photometry, no PSF-matched differencing.
- Synthetic data are used only in automated tests (`conftest.py::FakeArchive`), never in the app or the reports.
