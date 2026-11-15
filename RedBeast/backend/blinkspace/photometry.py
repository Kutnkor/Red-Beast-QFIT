"""Açıklık fotometrisi — **yeniden örneklenmemiş** ham cutout pikselleri üzerinde.

Önizleme veya hizalanmış (ara değerlenmiş) görüntüden ölçüm yapılmaz: yeniden örnekleme pikselleri
ilişkilendirir ve varyansı bozar. Burada IMAGE ve VARIANCE katmanları doğrudan kullanılır.

Sınırlar (raporlarda da belirtilir):
- Açıklık düzeltmesi uygulanmaz; değerler "açıklık akısı"dır. PSF kareden kareye değiştiği için
  mutlak akı değil, aynı dalga boyundaki göreli değişim anlamlıdır.
- Piksel katı açısı WCS'ten (SIP hariç) alınır; resmî katı açı haritasına göre fark < %1 düzeyindedir.
- Açıklıkta geçersiz piksel varsa ölçüm "yok" sayılır; doyma/doğrusalsızlık bayrağı varsa "güvenilmez".
"""
from __future__ import annotations

import math

import numpy as np
from astropy.wcs.utils import proj_plane_pixel_area
try:
    from photutils.aperture import CircularAperture
except Exception:  # noqa: BLE001 - the compiled extension can be missing or blocked by the operating system
    CircularAperture = None

from .quality import SATURATION_FLAGS, classify, flag_masks, flag_names_in
from .spx import SpxFrame

DEFAULT_R_AP = 2.0     # piksel (12.3″)
DEFAULT_R_IN = 4.0
DEFAULT_R_OUT = 7.0


def circular_weights(x: float, y: float, r: float, shape: tuple[int, int], samples: int = 4000) -> np.ndarray:
    """Fraction of each pixel covered by a circle (pixel centres at integer coordinates).

    Used when photutils cannot be imported. The chord of the circle is exact in y and integrated across each
    pixel in x with the midpoint rule; with 4000 samples the weights agree with photutils' ``method="exact"``
    to better than 1e-5 per pixel.
    """
    ny, nx = shape
    weights = np.zeros(shape, dtype=np.float64)
    i0, i1 = max(0, math.floor(x - r + 0.5)), min(nx - 1, math.floor(x + r + 0.5))
    j0, j1 = max(0, math.floor(y - r + 0.5)), min(ny - 1, math.floor(y + r + 0.5))
    steps = (np.arange(samples) + 0.5) / samples
    for i in range(i0, i1 + 1):
        xs = (i - 0.5) + steps
        half = np.sqrt(np.clip(r * r - (xs - x) ** 2, 0.0, None))
        low, high = y - half, y + half
        for j in range(j0, j1 + 1):
            weights[j, i] = float(np.mean(np.clip(high, j - 0.5, j + 0.5) - np.clip(low, j - 0.5, j + 0.5)))
    return weights


def aperture_photometry(frame: SpxFrame, ra_deg: float, dec_deg: float, r_ap: float = DEFAULT_R_AP,
                        r_in: float = DEFAULT_R_IN, r_out: float = DEFAULT_R_OUT) -> dict:
    x, y = frame.world_to_pixel(ra_deg, dec_deg)
    x, y = float(x[0]), float(y[0])
    ny, nx = frame.shape
    lam, bw = frame.wavelength_at(x, y)
    out = {
        "valid": False, "reason": None, "x": round(x, 2), "y": round(y, 2),
        "lam_um": None if not math.isfinite(float(lam)) else round(float(lam), 5),
        "bw_um": None if not math.isfinite(float(bw)) else round(float(bw), 5),
        "r_ap_px": r_ap, "annulus_px": [r_in, r_out],
        "flux_mjy": None, "err_mjy": None, "flags": {}, "saturated": False,
    }
    if not (math.isfinite(x) and math.isfinite(y)) or x < r_out or y < r_out or x > nx - 1 - r_out or y > ny - 1 - r_out:
        out["reason"] = "off_frame"
        return out
    masks = flag_masks(frame)
    if CircularAperture is None:
        w = circular_weights(x, y, r_ap, (ny, nx))
    else:
        w = CircularAperture((x, y), r=r_ap).to_mask(method="exact").to_image((ny, nx))
    inside = w > 0
    names = flag_names_in(frame, inside)
    out["flags"] = {k: v for k, v in names.items() if classify(k) != "info"}
    out["saturated"] = any(k in SATURATION_FLAGS for k in names)
    if np.any(masks.invalid & inside):
        out["reason"] = "invalid_pixels_in_aperture"
        return out
    yy, xx = np.mgrid[0:ny, 0:nx]
    rr = np.hypot(xx - x, yy - y)
    ann = (rr >= r_in) & (rr <= r_out) & ~masks.invalid & ~masks.suspect
    vals = frame.image[ann].astype(np.float64)
    if vals.size < 12:
        out["reason"] = "no_background_annulus"
        return out
    med = np.median(vals)
    sig = 1.4826 * np.median(np.abs(vals - med))
    for _ in range(4):
        keep = np.abs(vals - med) <= 3.0 * sig if sig > 0 else np.ones(vals.size, bool)
        if keep.all() or keep.sum() < 12:
            break
        vals = vals[keep]
        med = np.median(vals)
        sig = 1.4826 * np.median(np.abs(vals - med))
    bkg_err = 1.2533 * sig / math.sqrt(vals.size)
    img = frame.image.astype(np.float64)
    var = frame.variance.astype(np.float64)
    if not np.all(np.isfinite(var[inside])) or np.any(var[inside] < 0):
        out["reason"] = "invalid_variance"
        return out
    omega = float(proj_plane_pixel_area(frame.wcs.celestial)) * (math.pi / 180.0) ** 2  # sr / piksel
    # Yalnızca açıklık içindeki pikseller toplanır: açıklık dışındaki NaN'lar (0 × NaN) toplamı bozmamalı.
    net = float(np.sum(w[inside] * (img[inside] - med)))                               # MJy/sr · piksel
    var_sum = float(np.sum(w[inside] ** 2 * var[inside])) + float(np.sum(w[inside])) ** 2 * bkg_err ** 2
    to_mjy = omega * 1e9  # MJy/sr·piksel -> mJy
    out.update(
        valid=True,
        flux_mjy=net * to_mjy,
        err_mjy=math.sqrt(max(var_sum, 0.0)) * to_mjy,
        background_mjy_sr=float(med), background_sigma_mjy_sr=float(sig), n_annulus=int(vals.size),
        pixel_solid_angle_sr=omega,
        reliable=not out["saturated"],
    )
    if out["saturated"]:
        out["reason"] = "saturated_or_nonlinear"
    return out
