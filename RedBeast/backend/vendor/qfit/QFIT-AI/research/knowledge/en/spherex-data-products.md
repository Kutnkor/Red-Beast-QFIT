---
id: spherex-data-products
title: SPHEREx data products and releases
language: en
topic: spherex_data
mission: SPHEREx
data_release: DR1, QR3
version: 1
---
## Spectral Image (Level 2)
The basic SPHEREx science product is the Spectral Image, a multi-extension FITS file of about 70 MB. There is one file per detector per sky pointing. It has six extensions: IMAGE (calibrated surface brightness in MJy/sr, 2040 x 2040 pixels, zodiacal light not subtracted), FLAGS (per-pixel status bits), VARIANCE (variance of IMAGE in (MJy/sr)^2), ZODI (a model of the zodiacal background, not subtracted from IMAGE), EPSF (point-spread functions on a grid of zones; called PSF in QR2), and WCS-WAVE (a lookup table from pixel position to central wavelength and bandwidth). Not all six detectors are present for every observation.
Sources: spherex-data-products

## A spectral image is not a spectrum
Each detector sits behind a linear variable filter, so within one Spectral Image the wavelength changes with pixel position. One exposure therefore gives one wavelength for a given sky position, not a spectrum. A spectrum of a source is assembled from many exposures in which the source falls on different parts of the detectors. The WCS-WAVE table is meant for visualization; for science IRSA says to use the central-wavelength (CWAVE) and bandwidth (CBAND) extensions of the Spectral WCS calibration product.
Sources: spherex-data-products, irsa-tutorial-intro

## The six detector bands
Band 1: 0.75-1.09 micron, resolving power 39. Band 2: 1.10-1.62 micron, R 41. Band 3: 1.63-2.41 micron, R 41. Band 4: 2.42-3.82 micron, R 35. Band 5: 3.83-4.41 micron, R 112. Band 6: 4.42-5.00 micron, R 128. Detectors are numbered 1 to 6 and each Spectral Image covers one detector.
Sources: spherex-data-products

## All-Sky Cube
The All-Sky Cube exists only in Data Release 1. It is built from DR1 Spectral Images and covers the whole sky in 12,288 HEALPix tiles (order 5, NESTED), each about 1.8 x 1.8 degrees. A tile has 512 x 512 pixels of 12.9 arcseconds and 102 spectral channels (channels 1-17 from each of the six detectors). Its IMAGE extension is surface brightness in MJy/sr with zodiacal light subtracted. Known issues stated by IRSA: channels 51 and 52 contain no data, atmospheric emission such as the 1.083 micron helium line creates stripes, and the HPX projection looks distorted in many FITS viewers.
Sources: spherex-data-products, spherex-dr1

## Releases
IRSA lists these releases: the first Quick Release in July 2025, the reprocessed Quick Release 2 (QR2) in October 2025, Quick Release 3 (QR3) in September 2026 and Data Release 1 (DR1) in November 2026. DR1 Spectral Images are reprocessed versions of the QR2 images and are meant to be used together with QR3 as a uniformly processed set. QR2 is no longer searchable through the SIA2 service but stays downloadable until February 2027. A Flux Corrections calibration product exists for DR1 and QR3 to combine QR2 data (old gain) with QR3 data (new gain), so brightness values from different releases must not be compared directly without checking this.
Sources: irsa-spherex, spherex-dr1, spherex-data-access, spherex-data-products
