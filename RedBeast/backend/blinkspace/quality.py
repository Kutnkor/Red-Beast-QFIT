"""Kalite bayraklarının yorumlanması.

Bit numaraları sabit kodlanmaz; her dosyanın kendi tanımından (`SpxFrame.flag_defs`) ad ile bulunur.
Adlar üç sınıfa ayrılır:

- INVALID  : ölçüm yok / kullanılamaz. Piksel NaN yapılır, asla 0 ile doldurulmaz.
- SUSPECT  : ölçüm var ama kirlenmiş olabilir. Değer gösterilir, maske ayrı taşınır.
- INFO     : bilgi amaçlı (ör. SOURCE: bilinen kaynağa eşlenen piksel). Maske üretmez.

Sınıflandırma, IRSA "SPHEREx Source Discovery Tool" öğreticisindeki fotometri için kötü bayrak listesiyle
uyumludur (TRANSIENT, OVERFLOW, SUR_ERROR, PHANTOM, REFERENCE, NONFUNC, DICHROIC, MISSING_DATA, HOT, COLD,
FULLSAMPLE, PHANMISS, NONLINEAR, PERSIST, OUTLIER); QR2 v6.5+/QR3'te eklenen artefakt bayrakları SUSPECT
sayılır. Tanınmayan yeni adlar temkinli davranışla SUSPECT kabul edilir ve raporlanır.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .spx import SpxFrame

INVALID_FLAGS = frozenset({"NONFUNC", "MISSING_DATA", "SUR_ERROR", "HOT", "COLD", "PHANTOM", "REFERENCE"})
SUSPECT_FLAGS = frozenset({
    "TRANSIENT", "OVERFLOW", "NONLINEAR", "PERSIST", "OUTLIER", "PHANMISS", "DICHROIC", "FULLSAMPLE",
    "CROSSTALK", "GHOST", "GHOST_FPA", "GHOST_EXT", "STREAK", "BLOOM", "SNOWBALL", "HALO",
})
INFO_FLAGS = frozenset({"SOURCE"})
# Parlaklık ölçümünü güvenilmez kılan (doyma/doğrusalsızlık) bayraklar
SATURATION_FLAGS = frozenset({"OVERFLOW", "NONLINEAR"})


def classify(name: str) -> str:
    n = name.upper()
    if n in INVALID_FLAGS:
        return "invalid"
    if n in INFO_FLAGS:
        return "info"
    return "suspect"  # bilinen SUSPECT + tanınmayan adlar


def bitmask_for(flag_defs: dict[str, int], names) -> int:
    mask = 0
    for n in names:
        bit = flag_defs.get(n)
        if bit is not None:
            mask |= 1 << int(bit)
    return mask


@dataclass
class FlagMasks:
    invalid: np.ndarray   # bool: ölçüm yok (bayrak veya sonlu olmayan değer)
    suspect: np.ndarray   # bool: ölçüm var, şüpheli
    source: np.ndarray    # bool: bilinen kaynak pikseli (bilgi)
    unknown_names: tuple[str, ...]


def flag_masks(frame: SpxFrame) -> FlagMasks:
    defs = frame.flag_defs
    known = INVALID_FLAGS | SUSPECT_FLAGS | INFO_FLAGS
    unknown = tuple(sorted(n for n in defs if n not in known))
    inv_bits = bitmask_for(defs, [n for n in defs if classify(n) == "invalid"])
    sus_bits = bitmask_for(defs, [n for n in defs if classify(n) == "suspect"])
    src_bits = bitmask_for(defs, ["SOURCE"])
    invalid = ((frame.flags & inv_bits) != 0) | ~np.isfinite(frame.image)
    suspect = ((frame.flags & sus_bits) != 0) & ~invalid
    source = (frame.flags & src_bits) != 0
    return FlagMasks(invalid=invalid, suspect=suspect, source=source, unknown_names=unknown)


def flag_names_in(frame: SpxFrame, region: np.ndarray) -> dict[str, int]:
    """`region` (bool) içindeki piksellerde görülen bayrak adları ve piksel sayıları."""
    out: dict[str, int] = {}
    vals = frame.flags[region]
    for name, bit in sorted(frame.flag_defs.items(), key=lambda kv: kv[1]):
        n = int(np.count_nonzero(vals & (1 << int(bit))))
        if n:
            out[name] = n
    return out


def quality_summary(frame: SpxFrame, target_xy: tuple[float, float] | None = None, radius_px: float = 2.5) -> dict:
    """Kare kalite özeti (arayüz ve raporlar için)."""
    masks = flag_masks(frame)
    n = frame.image.size
    summary = {
        "n_pixels": int(n),
        "frac_invalid": round(float(masks.invalid.sum()) / n, 4),
        "frac_suspect": round(float(masks.suspect.sum()) / n, 4),
        "n_nonfinite": int(np.count_nonzero(~np.isfinite(frame.image))),
        "flags_present": flag_names_in(frame, np.ones(frame.shape, bool)),
        "unknown_flag_names": list(masks.unknown_names),
        "l1_dqa": frame.l1_dqa,
        "l2_dqa": frame.l2_dqa,
        "psf_fwhm_arcsec": frame.psf_fwhm_arcsec,
    }
    if target_xy is not None:
        ny, nx = frame.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        near = (xx - target_xy[0]) ** 2 + (yy - target_xy[1]) ** 2 <= radius_px ** 2
        inside = 0 <= target_xy[0] <= nx - 1 and 0 <= target_xy[1] <= ny - 1
        at = flag_names_in(frame, near) if near.any() else {}
        summary["target"] = {
            "in_cutout": bool(inside),
            "edge_px": round(float(min(target_xy[0], nx - 1 - target_xy[0], target_xy[1], ny - 1 - target_xy[1])), 1),
            "flags": {k: v for k, v in at.items() if classify(k) != "info"},
            "info_flags": {k: v for k, v in at.items() if classify(k) == "info"},
            "n_invalid": int(np.count_nonzero(masks.invalid & near)),
            "saturated": any(k in SATURATION_FLAGS for k in at),
        }
    return summary
