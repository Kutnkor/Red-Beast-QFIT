"""Önizleme görüntüleri (PNG). Önizlemeler yalnızca görsel inceleme içindir; ölçüm yapılmaz.

- Bir dizideki tüm kareler **aynı** siyah/beyaz sınırlarını ve aynı asinh eğrisini kullanır.
- Geçersiz pikseller saydamdır (alfa = 0); arayüz bunları desenli zeminle "ölçüm yok" olarak gösterir.
- PNG'nin ilk satırı kuzeydir: FITS dizisi düşeyde çevrilerek yazılır (kuzey yukarı, doğu solda).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def display_limits(images: list[np.ndarray], sigmas: list[float]) -> dict:
    """Arka planı çıkarılmış kareler için ortak görüntüleme sınırları."""
    finite = [im[np.isfinite(im)] for im in images]
    finite = [v for v in finite if v.size]
    sig = [s for s in sigmas if np.isfinite(s) and s > 0]
    sigma = float(np.median(sig)) if sig else (float(np.std(np.concatenate(finite))) if finite else 1.0)
    if not finite:
        return {"vmin": -1.0, "vmax": 1.0, "soft": 1.0, "sigma": sigma, "stretch": "asinh"}
    allv = np.concatenate(finite)
    vmin = -2.0 * sigma
    vmax = float(max(np.percentile(allv, 99.7), 25.0 * sigma))
    return {"vmin": float(vmin), "vmax": vmax, "soft": float(3.0 * sigma), "sigma": sigma, "stretch": "asinh"}


def stretch(image: np.ndarray, limits: dict) -> np.ndarray:
    """asinh germe -> uint8 [0, 255]. Sonlu olmayan değerler 0 döner (alfa ile ayrıca maskelenir)."""
    vmin, vmax, soft = limits["vmin"], limits["vmax"], max(limits["soft"], 1e-12)
    v = np.clip(np.nan_to_num(image.astype(np.float64), nan=vmin), vmin, vmax)
    y = np.arcsinh((v - vmin) / soft) / np.arcsinh((vmax - vmin) / soft)
    return np.clip(np.round(y * 255.0), 0, 255).astype(np.uint8)


def write_gray_png(path: Path, image: np.ndarray, invalid: np.ndarray, limits: dict) -> None:
    gray = stretch(image, limits)
    alpha = np.where(invalid | ~np.isfinite(image), 0, 255).astype(np.uint8)
    arr = np.dstack([gray, alpha])[::-1]  # kuzey yukarı
    Image.fromarray(arr, mode="LA").save(path, optimize=True)


def write_mask_png(path: Path, suspect: np.ndarray, not_comparable: np.ndarray) -> None:
    """Kalite katmanı: şüpheli pikseller turuncu, dalga boyu uyumsuz alan mavi (yarı saydam)."""
    ny, nx = suspect.shape
    rgba = np.zeros((ny, nx, 4), np.uint8)
    rgba[not_comparable] = (70, 140, 255, 110)
    rgba[suspect] = (255, 150, 0, 150)
    Image.fromarray(rgba[::-1], mode="RGBA").save(path, optimize=True)


def write_diff_png(path: Path, diff: np.ndarray, invalid: np.ndarray, scale: float) -> None:
    """Fark görüntüsü: orta gri = 0, beyaz = artış, siyah = azalış; doğrusal, ±scale."""
    s = max(float(scale), 1e-12)
    v = np.clip(np.nan_to_num(diff.astype(np.float64), nan=0.0) / s, -1.0, 1.0)
    gray = np.round((v * 0.5 + 0.5) * 255.0).astype(np.uint8)
    alpha = np.where(invalid | ~np.isfinite(diff), 0, 255).astype(np.uint8)
    Image.fromarray(np.dstack([gray, alpha])[::-1], mode="LA").save(path, optimize=True)
