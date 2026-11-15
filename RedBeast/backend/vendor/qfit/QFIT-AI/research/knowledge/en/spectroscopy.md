---
id: spectroscopy
title: Spectroscopy, brightness and units in SPHEREx data
language: en
topic: spectroscopy
version: 1
---
## Spectroscopy
Spectroscopy splits light into its wavelengths, as a prism makes a rainbow from sunlight. What the eye sees as colours are different wavelengths. SPHEREx works in the near-infrared, from 0.75 to 5.0 micron, beyond the red end of visible light.
Sources: jpl-spherex-presskit, spherex-goals

## Resolving power
Spectral resolving power R is the wavelength divided by the smallest wavelength difference that can be separated, R = lambda / delta-lambda; it has no unit. SPHEREx's resolving power is between 35 and 41 in bands 1 to 4 and 112 and 128 in bands 5 and 6. With R about 40, a channel at 1.4 micron is about 0.035 micron wide. This is low resolution: broad molecular absorption bands can be seen, narrow lines cannot be separated.
Sources: irsa-sia, spherex-data-products

## Surface brightness is not flux
SPHEREx Spectral Images give surface brightness in megajansky per steradian (MJy/sr): brightness per unit area of sky. To get the flux of a source, the pixel values must be summed over an aperture, the background subtracted, and the result multiplied by the solid angle of a pixel. IRSA's tutorial does this with aperture photometry and converts to millijansky, and states that the method is for visualization; for science it recommends IRSA's SPHEREx Spectrophotometry Tool. A single pixel value read by Q-FIT is a raw reading that still contains zodiacal light. It is not the flux of the object.
Sources: spherex-data-products, irsa-tutorial-hips

## Luminosity and flux
Luminosity is the total energy a star radiates per second; it is a property of the star. Flux is the energy received per unit area per second by the observer, so it depends on distance as well as on luminosity. Converting a measured flux to a luminosity needs the distance.
Sources: chandra-hr, atnf-hr-classifying
Verification: the definition of flux is standard physics and is not stated in the cited pages; citation needed.

## Molecules in cool atmospheres
Cool objects such as brown dwarfs have molecules in their atmospheres that absorb infrared light at particular wavelengths. In SPHEREx spectra of brown dwarfs the team reports signatures of water, carbon dioxide, carbon monoxide and methane, changing from object to object with temperature.
Sources: nasa-spherex-brown-dwarfs
