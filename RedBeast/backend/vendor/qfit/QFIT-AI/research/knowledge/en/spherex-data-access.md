---
id: spherex-data-access
title: How SPHEREx data are found and retrieved
language: en
topic: data_access
mission: SPHEREx
data_release: DR1, QR3
version: 1
---
## Searching the archive
SPHEREx data are served by the NASA/IPAC Infrared Science Archive (IRSA). Q-FIT searches with the IVOA Simple Image Access v2 (SIA2) service, which returns every image whose footprint intersects a circle on the sky. The searchable collections are spherex_dr1 and spherex_qr3 (wide survey), spherex_dr1_deep and spherex_qr3_deep (deep survey) and spherex_dr1_cube (All-Sky Cube tiles). New exposures appear in SIA2 about a day after they appear in IRSA's other interfaces.
Sources: spherex-data-access, irsa-sia

## What an archive record tells you
One archive record describes one file: observation identifier, collection, detector band, start and end time (Modified Julian Date), exposure time, wavelength limits in metres, resolving power, image centre, field of view and download address. In the records Q-FIT inspected, a Spectral Image has a field of view of about 3.5 degrees, a pixel scale of 6.15 arcseconds and an exposure time of about 113.6 seconds. The image centre is not the position of the object you searched for; the object can be anywhere inside the image.
Sources: irsa-live-query, irsa-tutorial-intro

## Cutouts
IRSA's cutout service returns a small part of a Spectral Image when "?center=RA,Dec&size=SIZE" (degrees) is appended to the file's on-premises address. The cutout keeps all extensions; IMAGE, FLAGS, VARIANCE and ZODI are trimmed and the wavelength table is remapped to the cutout.
Sources: spherex-data-access, spherex-data-products

## A catalog match is not an observation
Finding an object in SIMBAD or JPL Horizons shows that the object is catalogued. It does not show that SPHEREx observed it. Only an archive query that returns files covering the position establishes that, and even then the files show that the position was imaged, not that the object was detected in them.
Sources: qfit-spec
