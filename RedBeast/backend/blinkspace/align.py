"""Ortak gökyüzü ızgarasına hizalama.

Tüm kareler aynı hedef ızgaraya yeniden örneklenir: merkez (ra, dec) ICRS, TAN izdüşümü, kuzey yukarı,
doğu solda, piksel ölçeği SPHEREx doğal ölçeği (6.15″). Hizalama yalnızca dosyaların WCS'ine (TAN-SIP)
dayanır; hiçbir kaynak karelerde "sabitlenmez", dolayısıyla gerçek hareket korunur.

Maskeler görüntü gibi ortalanmaz:
- geçersiz piksel maskesi: girişte NaN yapılır; çift doğrusal ara değerleme NaN'ı komşulara yayar
  (temkinli büyüme). Ayrıca maske kayan sayı olarak yeniden örneklenir ve > 0 olan her çıkış pikseli
  geçersiz sayılır.
- şüpheli maske: en yakın komşu ile taşınır.
- bayrak bitleri hiçbir zaman ara değerlenmez.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from astropy.wcs import WCS
from reproject import reproject_interp

from .quality import flag_masks
from .spx import SpxFrame

NATIVE_PIXSCALE_ARCSEC = 6.15


def target_grid(ra_deg: float, dec_deg: float, fov_arcmin: float, pixscale_arcsec: float = NATIVE_PIXSCALE_ARCSEC) -> tuple[WCS, tuple[int, int]]:
    """Hedef ızgara WCS'i ve (ny, nx). Boyut tektir; merkez piksel tam olarak (ra, dec)'tir."""
    n = int(round(fov_arcmin * 60.0 / pixscale_arcsec))
    if n % 2 == 0:
        n += 1
    n = max(n, 5)
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra_deg % 360.0, dec_deg]
    w.wcs.crpix = [(n + 1) / 2.0, (n + 1) / 2.0]
    w.wcs.cdelt = [-pixscale_arcsec / 3600.0, pixscale_arcsec / 3600.0]
    w.wcs.cunit = ["deg", "deg"]
    w.wcs.radesys = "ICRS"
    w.array_shape = (n, n)
    return w, (n, n)


def grid_to_dict(w: WCS, shape: tuple[int, int]) -> dict:
    """Arayüzün gökyüzü<->piksel dönüşümü için gereken en küçük WCS tanımı (TAN, döndürmesiz)."""
    return {
        "projection": "TAN",
        "frame": "ICRS",
        "crval": [float(w.wcs.crval[0]), float(w.wcs.crval[1])],
        "crpix": [float(w.wcs.crpix[0]), float(w.wcs.crpix[1])],  # 1-tabanlı FITS
        "cdelt": [float(w.wcs.cdelt[0]), float(w.wcs.cdelt[1])],
        "nx": int(shape[1]),
        "ny": int(shape[0]),
        "pixscale_arcsec": float(abs(w.wcs.cdelt[1]) * 3600.0),
        "orientation": "north_up_east_left",
    }


@dataclass
class AlignedFrame:
    image: np.ndarray        # MJy/sr, geçersiz/kapsam dışı = NaN
    invalid: np.ndarray      # bool: ölçüm yok (kapsam dışı dahil)
    suspect: np.ndarray      # bool
    coverage: np.ndarray     # bool: karenin ayak izi içinde mi
    lam_um: np.ndarray       # her çıkış pikselindeki merkez dalga boyu
    bw_um: np.ndarray
    variance: np.ndarray     # yaklaşık (çift doğrusal); yalnızca görsel S/N için


def reproject_frame(frame: SpxFrame, out_wcs: WCS, shape: tuple[int, int]) -> AlignedFrame:
    masks = flag_masks(frame)
    img = frame.image.astype(np.float64).copy()
    img[masks.invalid] = np.nan
    out, _ = reproject_interp((img, frame.wcs), out_wcs, shape_out=shape, order="bilinear")
    # Geometrik kapsam, NaN içermeyen maske dizisinin ayak izinden alınır (görüntünün ayak izi NaN'ları da dışlar).
    inv_f, footprint = reproject_interp((masks.invalid.astype(np.float64), frame.wcs), out_wcs, shape_out=shape, order="bilinear")
    cov = footprint > 0
    invalid = ~cov | ~np.isfinite(out) | (np.nan_to_num(inv_f, nan=1.0) > 1e-6)
    out = np.where(invalid, np.nan, out)
    sus_f, _ = reproject_interp((masks.suspect.astype(np.float64), frame.wcs), out_wcs, shape_out=shape, order="nearest-neighbor")
    suspect = (np.nan_to_num(sus_f, nan=0.0) > 0.5) & ~invalid
    var = frame.variance.astype(np.float64).copy()
    var[masks.invalid] = np.nan
    var_out, _ = reproject_interp((var, frame.wcs), out_wcs, shape_out=shape, order="bilinear")

    # Dalga boyu haritası: çıkış pikseli -> gökyüzü -> giriş pikseli -> dedektör koordinatı -> tablo
    ny, nx = shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    ra, dec = out_wcs.all_pix2world(xx.ravel(), yy.ravel(), 0)
    px, py = frame.wcs.all_world2pix(ra, dec, 0, quiet=True)
    lam, bw = frame.wavelength_at(px, py)
    return AlignedFrame(
        image=out.astype(np.float32),
        invalid=invalid,
        suspect=suspect,
        coverage=cov,
        lam_um=np.asarray(lam, np.float32).reshape(shape),
        bw_um=np.asarray(bw, np.float32).reshape(shape),
        variance=np.where(invalid, np.nan, var_out).astype(np.float32),
    )


def comparable_mask(aligned: AlignedFrame, lam_ref_um: float, bw_ref_um: float, tol: float) -> np.ndarray:
    """Dalga boyu referansa `tol × Δλ` içinde olan pikseller (zaman karşılaştırmasına uygun alan)."""
    with np.errstate(invalid="ignore"):
        return np.isfinite(aligned.lam_um) & (np.abs(aligned.lam_um - lam_ref_um) <= tol * bw_ref_um)


def robust_background(image: np.ndarray, exclude: np.ndarray, n_iter: int = 5, clip: float = 3.0) -> tuple[float, float, int]:
    """Sigma-kırpmalı ortanca arka plan ve MAD tabanlı gürültü (σ ≈ 1.4826·MAD).

    `exclude`: arka plan kestirimine girmeyecek pikseller (geçersiz, şüpheli, bilinen kaynak).
    Döner: (arka plan, sigma, kullanılan piksel sayısı). Yeterli piksel yoksa (nan, nan, n).
    """
    vals = image[~exclude & np.isfinite(image)].astype(np.float64)
    if vals.size < 20:
        return float("nan"), float("nan"), int(vals.size)
    med = np.median(vals)
    sig = 1.4826 * np.median(np.abs(vals - med))
    for _ in range(n_iter):
        if not np.isfinite(sig) or sig <= 0:
            break
        keep = np.abs(vals - med) <= clip * sig
        if keep.sum() < 20 or keep.all():
            break
        vals = vals[keep]
        med = np.median(vals)
        sig = 1.4826 * np.median(np.abs(vals - med))
    return float(med), float(sig), int(vals.size)


def centroid(image: np.ndarray, x0: float, y0: float, half: int = 2) -> tuple[float, float, float] | None:
    """(x0, y0) çevresindeki (2·half+1)² kutuda arka planı çıkarılmış akı-ağırlıklı merkez.

    Kutuda geçersiz piksel varsa veya net akı pozitif değilse None. Döner: (x, y, net akı toplamı).
    Yalnızca hizalama denetimi içindir; alt-örneklemeli PSF nedeniyle ~0.1–0.3 piksel hassasiyet beklenir.
    """
    ny, nx = image.shape
    ix, iy = int(round(x0)), int(round(y0))
    if ix - half - 2 < 0 or iy - half - 2 < 0 or ix + half + 2 >= nx or iy + half + 2 >= ny:
        return None
    box = image[iy - half: iy + half + 1, ix - half: ix + half + 1].astype(np.float64)
    if not np.all(np.isfinite(box)):
        return None
    ring = image[iy - half - 2: iy + half + 3, ix - half - 2: ix + half + 3].astype(np.float64).copy()
    ring[2:-2, 2:-2] = np.nan
    rv = ring[np.isfinite(ring)]
    if rv.size < 8:
        return None
    net = box - np.median(rv)
    net[net < 0] = 0.0
    tot = net.sum()
    if tot <= 0:
        return None
    yy, xx = np.mgrid[iy - half: iy + half + 1, ix - half: ix + half + 1]
    return float((net * xx).sum() / tot), float((net * yy).sum() / tot), float(tot)
