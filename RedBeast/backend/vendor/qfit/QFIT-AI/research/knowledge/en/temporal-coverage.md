---
id: temporal-coverage
title: Time coverage and comparing SPHEREx observations
language: en
topic: temporal_analysis
mission: SPHEREx
version: 1
---
## Survey cadence
SPHEREx maps the whole sky four times in its nominal 25-month mission, so a typical sky position is revisited about every six months. During one visit a position is covered by several exposures taken close together in time, because the telescope steps across the sky and the position passes over different detectors.
Sources: spherex-goals, spherex-about, irsa-live-query

## There is no uniform time series
The exposures of one sky position are clustered into visits separated by long gaps. They are not evenly spaced. A timeline must show the actual exposure times and leave the gaps empty; a gap means "not observed", never "no change". Deep-survey fields are observed far more often than typical wide-survey positions.
Sources: spherex-data-access, qfit-spec

## Two exposures are rarely at the same wavelength
Because the wavelength depends on where the position falls on the detector, two exposures of the same position usually measure different wavelengths even when they come from the same detector band. The Q-FIT team measured this on real QR2 files in the south ecliptic pole deep field: four exposure pairs taken 2 minutes, 1.5 hours, 1 day and 6 months apart all differed in wavelength by about one bandwidth or more. A brightness difference between two such exposures is therefore not evidence that the source changed. This measurement was made on QR2 data and should be rechecked for DR1 and QR3.
Sources: qfit-milestone-report, spherex-data-products

## What can be compared
A fair comparison in brightness needs the same detector band, nearly the same wavelength at the target position, and the same processing release. Changes in position (motion) can be judged between exposures at different wavelengths, as long as the source is visible in both. Any apparent change found this way is a candidate for human review, not a detection.
Sources: qfit-milestone-report, qfit-spec
