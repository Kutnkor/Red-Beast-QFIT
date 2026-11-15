# Motion model

## model

The 3D scenes propagate catalogue astrometry as a Cartesian ICRS position and a constant
space velocity between 2000 and 2100. Right ascension proper motion includes cos(declination).
The Three.js presentation uses the coordinate order (ICRS x, ICRS z, ICRS y), with +Y north.
One neighbourhood unit is one parsec. Missing radial velocity is represented by an explicit
zero-velocity assumption; it is not a measured zero. Annual parallax, spacecraft viewpoint
and orbital motion are not included in this catalogue space-motion model.

The stellar surface and limb darkening are representative. Its colour follows a
temperature-labelled blackbody calculation when a temperature exists. A source-cited
radius can parameterize a compressed visual scale, but the drawn diameter is not an
angular-size measurement. A cool infrared source can be nearly invisible in visible
light. Neither the texture nor its surrounding animation is a resolved SPHEREx image.

SPHEREx time stacks contain the real, individually dated image planes. The planes do not
interpolate or animate the image pixels. A line through predicted catalogue positions is a
computed guide. Measured centroids are separate and can be missing, saturated or blended.
The co-moving stack is a display product, not photometry; static sources become smeared.

Sources: the application's source-labelled catalogue and reference constants, `SPEC.md`
rules 7–10, `docs/METHOD.md`, and the motion golden tests. Numerical results must be taken
from the current catalogue/context or a dated report, not inferred from this description.

## source-labelled-stellar-models

The five curated profiles served at `/api/models` cite their parameter sources and mark
measured, computed, representative or assumed values. Missing radius or temperature
values stay missing. The interface exposes the source parameters separately from the
drawing. The resource is `backend/blinkspace/resources/stellar_profiles.json`.

Barnard's Star has a representative active M-dwarf environment. Epsilon Indi B contains
two T-dwarf components; the display can illustrate a binary orbit without claiming a
measured orbital phase or sky orientation. WISE 0855 uses a cool Y-dwarf atmosphere
representation. RW Aurigae includes a schematic disk, jets and dust obscuration. R Draconis
includes illustrative pulsation and dust outflow. A sourced pulsation period does not
establish the displayed phase, angular radius or outflow geometry.

These environment animations explain source-supported phenomena. Particle trajectories,
texture patterns, apparent separations and animation speeds are representative unless
a specific displayed quantity has an explicit source and epistemic label. They are not
time-resolved images or hydrodynamic simulations.
