"""Blackbody temperature to an sRGB colour.

Method: integrate the Planck spectrum against the CIE 1931 2-degree colour matching
functions to get XYZ, convert to linear sRGB, scale so the brightest channel is 1,
and apply the sRGB transfer curve. Only the hue is kept; brightness is not encoded.

Sources for the constants in this file:
- Colour matching functions: the multi-lobe Gaussian fit of Wyman, Sloan and Shirley,
  "Simple Analytic Approximations to the CIE XYZ Color Matching Functions", Journal of
  Computer Graphics Techniques 2(2), 2013, Table 1 / Listing 1. https://jcgt.org/published/0002/02/01/
- XYZ to linear sRGB matrix and transfer curve: IEC 61966-2-1 (sRGB, D65 white point).
- h, c, k: exact SI defining constants (2019 redefinition).
"""

from __future__ import annotations

import math

MIN_TEMPERATURE_K = 1000.0
MAX_TEMPERATURE_K = 40000.0

_H = 6.62607015e-34
_C = 2.99792458e8
_K = 1.380649e-23

# (amplitude, centre nm, inverse width below centre, inverse width above centre)
_X_LOBES = ((0.362, 442.0, 0.0624, 0.0374), (1.056, 599.8, 0.0264, 0.0323), (-0.065, 501.1, 0.0490, 0.0382))
_Y_LOBES = ((0.821, 568.8, 0.0213, 0.0247), (0.286, 530.9, 0.0613, 0.0322))
_Z_LOBES = ((1.217, 437.0, 0.0845, 0.0278), (0.681, 459.0, 0.0385, 0.0725))

_XYZ_TO_LINEAR_SRGB = (
    (3.2406, -1.5372, -0.4986),
    (-0.9689, 1.8758, 0.0415),
    (0.0557, -0.2040, 1.0570),
)

_WAVELENGTHS_NM = range(380, 781, 5)


def _fit(lobes, wave_nm: float) -> float:
    total = 0.0
    for amplitude, centre, below, above in lobes:
        t = (wave_nm - centre) * (below if wave_nm < centre else above)
        total += amplitude * math.exp(-0.5 * t * t)
    return total


def _planck(wave_nm: float, temperature_k: float) -> float:
    wave_m = wave_nm * 1e-9
    return 1.0 / (wave_m**5 * math.expm1(_H * _C / (wave_m * _K * temperature_k)))


def _srgb_encode(linear: float) -> float:
    if linear <= 0.0031308:
        return 12.92 * linear
    return 1.055 * linear ** (1 / 2.4) - 0.055


def temperature_to_rgb(temperature_k: float) -> tuple[int, int, int]:
    """sRGB colour (0-255 per channel) of a blackbody at `temperature_k`.

    Temperatures outside 1000-40000 K are clamped to that range: below it a blackbody
    emits almost no visible light, above it the colour no longer changes visibly.
    """
    if not math.isfinite(temperature_k) or temperature_k <= 0:
        raise ValueError(f"temperature_k must be a finite number above 0, got {temperature_k!r}")
    t = min(max(float(temperature_k), MIN_TEMPERATURE_K), MAX_TEMPERATURE_K)

    x = y = z = 0.0
    for wave in _WAVELENGTHS_NM:
        power = _planck(wave, t)
        x += power * _fit(_X_LOBES, wave)
        y += power * _fit(_Y_LOBES, wave)
        z += power * _fit(_Z_LOBES, wave)

    linear = [max(row[0] * x + row[1] * y + row[2] * z, 0.0) for row in _XYZ_TO_LINEAR_SRGB]
    peak = max(linear)
    r, g, b = (round(255 * _srgb_encode(v / peak)) for v in linear)
    return (r, g, b)
