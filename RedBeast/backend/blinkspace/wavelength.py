"""Dalga boyu: SPHEREx'te her dedektör pikseli LVF nedeniyle farklı bir merkez dalga boyu görür.

- `WaveTable`: bir dosyanın `WCS-WAVE` arama tablosu (dedektörün 1-tabanlı FITS koordinatlarında X, Y kontrol
  noktaları ve her düğümde [merkez dalga boyu, bant genişliği] µm). Çift doğrusal ara değerleme.
  Resmî belgeye göre bu tablo ~1 nm doğruluktadır ve görselleştirme/seçim içindir.
- `WaveModel`: dedektör başına bir `WaveTable`; indirme öncesi dalga boyu öngörüsü için.
- `predict_detector_pixel`: arşiv ayak izinden (4 köşe) hedefin yaklaşık dedektör pikseli.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DETECTOR_SIZE = 2040


@dataclass(frozen=True)
class WaveTable:
    x: np.ndarray       # (nx,) artan, 1-tabanlı dedektör koordinatı
    y: np.ndarray       # (ny,)
    values: np.ndarray  # (ny, nx, 2): [..., 0]=dalga boyu µm, [..., 1]=bant genişliği µm

    def __post_init__(self):
        if self.values.shape != (len(self.y), len(self.x), 2):
            raise ValueError(f"WCS-WAVE boyutu uyumsuz: {self.values.shape} vs ({len(self.y)}, {len(self.x)}, 2)")
        if np.any(np.diff(self.x) < 0) or np.any(np.diff(self.y) < 0):
            raise ValueError("WCS-WAVE kontrol noktaları artan olmalı")

    def evaluate(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        """(dalga boyu, bant genişliği) µm. Tablo dışı noktalar NaN döner (dışa değerleme yapılmaz)."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        xs, ys = self.x.astype(float), self.y.astype(float)
        inside = (x >= xs[0]) & (x <= xs[-1]) & (y >= ys[0]) & (y <= ys[-1]) & np.isfinite(x) & np.isfinite(y)
        xc = np.clip(np.nan_to_num(x, nan=xs[0]), xs[0], xs[-1])
        yc = np.clip(np.nan_to_num(y, nan=ys[0]), ys[0], ys[-1])
        ix = np.clip(np.searchsorted(xs, xc, side="right") - 1, 0, len(xs) - 2)
        iy = np.clip(np.searchsorted(ys, yc, side="right") - 1, 0, len(ys) - 2)
        dx = xs[ix + 1] - xs[ix]
        dy = ys[iy + 1] - ys[iy]
        # Tekrarlanan kontrol noktası (sıfır genişlikli aralık) durumunda kesir 0 alınır.
        tx = np.where(dx > 0, (xc - xs[ix]) / np.where(dx > 0, dx, 1.0), 0.0)
        ty = np.where(dy > 0, (yc - ys[iy]) / np.where(dy > 0, dy, 1.0), 0.0)
        v = self.values
        out = []
        for k in (0, 1):
            v00 = v[iy, ix, k]
            v01 = v[iy, ix + 1, k]
            v10 = v[iy + 1, ix, k]
            v11 = v[iy + 1, ix + 1, k]
            val = (1 - ty) * ((1 - tx) * v00 + tx * v01) + ty * ((1 - tx) * v10 + tx * v11)
            out.append(np.where(inside, val, np.nan))
        return out[0], out[1]

    def to_dict(self) -> dict:
        return {"x": self.x.tolist(), "y": self.y.tolist(), "values": np.round(self.values.astype(float), 7).tolist()}

    @staticmethod
    def from_dict(d: dict) -> "WaveTable":
        return WaveTable(np.asarray(d["x"], float), np.asarray(d["y"], float), np.asarray(d["values"], float))

    @staticmethod
    def from_hdu(hdu) -> "WaveTable":
        """`WCS-WAVE` BinTable katmanından okur (sütunlar ada göre: X, Y, VALUES)."""
        row = hdu.data[0]
        x = np.asarray(row["X"], float).ravel()
        y = np.asarray(row["Y"], float).ravel()
        v = np.asarray(row["VALUES"], float)
        if v.shape != (len(y), len(x), 2):
            v = v.reshape(len(y), len(x), 2)
        return WaveTable(x, y, v)


class WaveModel:
    """Dedektör başına dalga boyu tablosu (indirme öncesi öngörü için)."""

    def __init__(self, tables: dict[int, WaveTable], sources: dict[int, dict] | None = None):
        self.tables = tables
        self.sources = sources or {}

    def evaluate(self, detector: int, x, y):
        return self.tables[detector].evaluate(x, y)

    @staticmethod
    def load(path: Path) -> "WaveModel":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        tables = {int(k): WaveTable.from_dict(v["table"]) for k, v in raw["detectors"].items()}
        sources = {int(k): v.get("source", {}) for k, v in raw["detectors"].items()}
        return WaveModel(tables, sources)

    def save(self, path: Path, note: str = "") -> None:
        doc = {
            "note": note,
            "detectors": {str(k): {"source": self.sources.get(k, {}), "table": t.to_dict()} for k, t in sorted(self.tables.items())},
        }
        Path(path).write_text(json.dumps(doc, indent=1), encoding="utf-8")


def _gnomonic(ra, dec, ra0, dec0):
    """Teğet düzlem (ξ, η) derece; ξ doğuya, η kuzeye."""
    ra, dec, ra0, dec0 = (np.radians(np.asarray(v, float)) for v in (ra, dec, ra0, dec0))
    cosc = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    xi = np.cos(dec) * np.sin(ra - ra0) / cosc
    eta = (np.cos(dec0) * np.sin(dec) - np.sin(dec0) * np.cos(dec) * np.cos(ra - ra0)) / cosc
    return np.degrees(xi), np.degrees(eta)


def predict_detector_pixel(footprint, ra_deg: float, dec_deg: float) -> tuple[float, float]:
    """Ayak izi köşelerinden hedefin yaklaşık 1-tabanlı dedektör pikseli.

    Köşe sırası gerçek dosyalarla doğrulanmıştır: (1,1), (N,1), (N,N), (1,N). Hedef konumu teğet nokta
    alınır; köşeler teğet düzleme izdüşürülür ve en küçük kareler afin dönüşümle piksele çevrilir.
    SIP bozulması yok sayıldığından doğruluk birkaç pikseldir; LVF eğimi (~180 piksel / çözünürlük öğesi)
    yanında ihmal edilebilir. Kesin değer indirme sonrası dosyanın WCS'inden hesaplanır.
    """
    fp = np.asarray(footprint, float)
    if fp.shape != (4, 2):
        raise ValueError("ayak izi 4 köşe olmalı")
    xi, eta = _gnomonic(fp[:, 0], fp[:, 1], ra_deg, dec_deg)
    n = float(DETECTOR_SIZE)
    px = np.array([1.0, n, n, 1.0])
    py = np.array([1.0, 1.0, n, n])
    a = np.column_stack([xi, eta, np.ones(4)])
    cx, *_ = np.linalg.lstsq(a, px, rcond=None)
    cy, *_ = np.linalg.lstsq(a, py, rcond=None)
    # hedef teğet noktadadır: (ξ, η) = (0, 0)
    return float(cx[2]), float(cy[2])


def edge_distance(x: float, y: float) -> float:
    """Dedektör kenarına en yakın uzaklık (piksel); negatifse dedektör dışında."""
    n = DETECTOR_SIZE
    return float(min(x - 1.0, n - x, y - 1.0, n - y))


def resolving_power(lam_um: float, bw_um: float) -> float:
    return lam_um / bw_um if bw_um and math.isfinite(bw_um) and bw_um > 0 else float("nan")
