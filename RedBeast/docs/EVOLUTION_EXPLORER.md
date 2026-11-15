# Three.js evolution and spatial explorer

The user authorized two separate time scales on 2026-11-14. This supersedes the earlier plan's exclusion of lifecycle modelling. Neither clock modifies, morphs or synthesizes SPHEREx image frames.

## Independent views

- **Observed system:** adopted catalogue/profile values, with a separate optional illustrative surface/flow clock. The 2000–2100 calendar controls only the existing linear ICRS space motion. Changing the calendar does not age the photosphere.
- **Evolution:** five published theoretical comparison tracks. The selected target suggests a class-related track; the displayed initial mass is a model choice, not a measured mass or a fitted age for that target. A model selector exposes that choice. The slider advances through published samples (EEP progress for MIST), not equal year intervals. Age, temperature, radius, luminosity and remaining mass come from the same interpolated row pair. Playback stops at the source boundary.
- **Spatial search:** the same heliocentric Cartesian propagation supplies the map, RA/Dec readout and nearest-direction ranking. Accepts a name or `RA, Dec` in decimal degrees. Only the loaded local catalogue is ranked; angular separation is displayed and no identification is inferred. The existing coordinate archive form remains available for real SPHEREx searches. Targets beyond 15 pc remain explicitly labelled direction indicators in the local map.

## Primary sources and limits

| Table | Selected initial masses | Scope |
|---|---|---|
| [MIST v1.2](https://mist.science/model_grids.html), non-rotating, [Fe/H]=0 | 1 and 1.4 M☉ | 1,710 EEP rows each, pre-main sequence through the white-dwarf cooling boundary; no subsequent cooling invented. This pins a documented version, not a claim to use the newest grid. |
| [BHAC15](https://perso.ens-lyon.fr/isabelle.baraffe/BHAC15dir/) | 0.15 M☉ | 432 rows, low-mass contraction/evolution, ending around 10 Gyr. No red-giant/explosion fate is attached to this table. |
| [ATMO 2020](https://perso.ens-lyon.fr/isabelle.baraffe/ATMO2020/) | 0.005 and 0.05 M☉ | Chemical-equilibrium substellar cooling tracks, 40 and 15 rows respectively after retaining only Teff < 2,000 K, the authors' stated validity range. The lower-mass table reaches below 250 K. Model assumptions are not an age/mass fit for WISE 0855 or either Epsilon Indi component. |

Column units and phase definitions follow [MIST's column/EEP guide](https://mist.science/README_tables.pdf), the BHAC15 file header and ATMO's evolutionary-track README. ATMO's luminosity values are logarithmic despite the abbreviated header label; the converted radii, temperatures and luminosities pass a Stefan–Boltzmann consistency check. Solar-composition assumptions, unknown target metallicities, unknown/uncertain target ages and unresolved binaries limit any target-specific interpretation.

The bundled `frontend/src/three/data/evolution.json` contains the selected original samples, source URLs and SHA-256s. `tools/prepare_evolution.py` reproduces the extraction from the downloaded files under ignored `evidence/evolution-sources`. MIST archive: `MIST_v1.2_feh_p0.00_afe_p0.0_vvcrit0.0_EEPS.txz`; take `00100M.track.eep` and `00140M.track.eep`. ATMO archive: `ATMO_2020_models.tar.gz`; take `evolutionary_tracks/ATMO_CEQ/MKO_WISE_IRAC/{0.005,0.05}_ATMO_CEQ_vega.txt` as `atmo-{mass}.txt`. BHAC15 filename: `BHAC15_tracks+structure`. No network is needed at runtime.

## Rendering

The canvas occupies its own DOM rectangle. ResizeObserver updates both drawing dimensions and the camera aspect. Close-up framing ignores the remote solar-reference circle; context framing includes it and the motion trail. Camera panning is retained when the year changes. The sky's transparent points now depth-test at the far plane so they cannot shine through an opaque stellar surface.

The catalogue surfaces retain their documented square-root display radius. Evolution uses `0.45 + 1.2 log10(1 + R/R☉)` to keep contraction and expansion legible, explicitly labelled as log compression. The camera's framing remains fixed over a selected evolution track so radius changes stay visible. Temperature controls the normalized blackbody colour (existing 1,000–40,000 K approximation); cold bodies are deliberately dark. This is not a radiometrically calibrated image. Surface granulation, giant cells, clouds, magnetic arches, funnels and flow tracers are procedural illustrations. MIST mass loss controls illustrative tracer density, not a solved wind velocity or density field. No supernova, planet, measured surface map or new discovery is invented.

## Validation

197 frontend tests passed on the final revision, including source-row monotonicity, finite values, Stefan–Boltzmann consistency, boundary clamping, lack of extrapolation, independent clocks, model restoration, RA wrap/poles and position round-trip. Final results and browser checks are recorded in `reports/evolution-validation.json`. Original backend science resources and public FITS files are unchanged. This work does not revalidate the quality or recency of every adopted astrometric catalogue value; e.g. RW Aur's inherited distance is based on the cited older Hipparcos parallax.
