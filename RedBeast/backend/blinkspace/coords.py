"""Koordinat ayrıştırma ve doğrulama.

Kabul edilen biçimler
- RA: ondalık derece (`269.452`), ondalık saat (birim `hour`), altmışlık saat
  (`17h57m48.5s`, `17:57:48.5`, `17 57 48.5`) veya altmışlık derece (`269d27m07s`).
- Dec: ondalık derece (`-7.245`), altmışlık derece (`-07d14m42.53s`, `-07:14:42.53`, `-07 14 42.53`).

Birimler açıktır: `ra_unit` "deg", "hour" veya "auto" olabilir. "auto" yalnızca biçim kesin olduğunda
(saat/dakika işaretleri, iki nokta, üç parça) saat varsayar; yalın sayı derecedir.
Çıktı ICRS derecedir; RA [0, 360) aralığına sarılır ve sarma bir not olarak döner.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


class CoordinateError(ValueError):
    """Geçersiz koordinat girişi. `code` arayüzde çevrilebilir bir hata anahtarıdır."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SkyPosition:
    ra_deg: float
    dec_deg: float
    notes: tuple[str, ...] = field(default_factory=tuple)


_NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_SEX = re.compile(
    r"^\s*(?P<sign>[+\-−–])?\s*(?P<a>\d+(?:\.\d+)?)\s*(?P<u1>[hd°:\s])\s*"
    r"(?P<b>\d+(?:\.\d+)?)\s*(?P<u2>[m'′:\s])\s*"
    r"(?:(?P<c>\d+(?:\.\d+)?)\s*(?P<u3>[s\"″]|'')?)?\s*$",
    re.IGNORECASE,
)
_PLAIN = re.compile(rf"^\s*(?P<v>{_NUM})\s*(?P<u>deg|d|°|h|hr|hours?)?\s*$", re.IGNORECASE)


def _clean(text: object) -> str:
    if isinstance(text, bool):
        raise CoordinateError("not_a_number", "Koordinat sayı olmalı.")
    if isinstance(text, (int, float)):
        if not math.isfinite(float(text)):
            raise CoordinateError("not_finite", "Koordinat sonlu bir sayı olmalı.")
        return repr(float(text))
    if not isinstance(text, str):
        raise CoordinateError("not_a_number", "Koordinat metin veya sayı olmalı.")
    s = text.strip().replace("−", "-").replace("–", "-").replace(",", ".")
    if not s:
        raise CoordinateError("empty", "Koordinat boş.")
    if len(s) > 40:
        raise CoordinateError("too_long", "Koordinat metni çok uzun.")
    return s


def _sexagesimal(s: str) -> tuple[float, str, bool] | None:
    """(değer, birim-ipucu 'h'|'d'|'', negatif_mi) döndürür; eşleşmezse None."""
    m = _SEX.match(s)
    if not m:
        return None
    a, b = float(m["a"]), float(m["b"])
    c = float(m["c"]) if m["c"] is not None else 0.0
    if "." in m["a"]:
        raise CoordinateError("bad_sexagesimal", "Altmışlık gösterimde ilk alan tam sayı olmalı.")
    if "." in m["b"] and m["c"] is not None:
        raise CoordinateError("bad_sexagesimal", "Saniye verildiğinde dakika tam sayı olmalı.")
    if not (0 <= b < 60) or not (0 <= c < 60):
        raise CoordinateError("bad_sexagesimal", "Dakika ve saniye 0 ile 60 arasında olmalı.")
    value = a + b / 60.0 + c / 3600.0
    u1 = m["u1"].lower()
    hint = "h" if u1 == "h" else ("d" if u1 in ("d", "°") else "")
    return value, hint, m["sign"] in ("-", "−", "–")


def parse_ra(text: object, unit: str = "auto") -> tuple[float, tuple[str, ...]]:
    """RA'yı dereceye çevirir. Dönen notlar: 'ra_wrapped', 'ra_assumed_hours', 'ra_assumed_degrees'."""
    if unit not in ("auto", "deg", "hour"):
        raise CoordinateError("bad_unit", "RA birimi 'deg', 'hour' veya 'auto' olmalı.")
    s = _clean(text)
    notes: list[str] = []
    sex = _sexagesimal(s)
    if sex is not None:
        value, hint, neg = sex
        if neg:
            raise CoordinateError("ra_negative_sexagesimal", "Altmışlık RA negatif olamaz.")
        if hint == "h" and unit == "deg":
            raise CoordinateError("unit_mismatch", "RA saat biçiminde yazılmış ama birim derece seçili.")
        if hint == "d" and unit == "hour":
            raise CoordinateError("unit_mismatch", "RA derece biçiminde yazılmış ama birim saat seçili.")
        is_hours = hint == "h" or (hint == "" and unit != "deg")
        if hint == "" and unit == "auto":
            notes.append("ra_assumed_hours")
        if is_hours:
            if value > 24.0:
                raise CoordinateError("ra_out_of_range", "RA saat olarak 0–24 aralığında olmalı.")
            deg = value * 15.0
        else:
            deg = value
    else:
        m = _PLAIN.match(s)
        if not m:
            raise CoordinateError("not_a_number", "RA anlaşılamadı.")
        value = float(m["v"])
        if not math.isfinite(value):
            raise CoordinateError("not_finite", "RA sonlu bir sayı olmalı.")
        u = (m["u"] or "").lower()
        suffix_hours = u.startswith("h")
        suffix_deg = u in ("deg", "d", "°")
        if suffix_hours and unit == "deg":
            raise CoordinateError("unit_mismatch", "RA saat birimiyle yazılmış ama birim derece seçili.")
        if suffix_deg and unit == "hour":
            raise CoordinateError("unit_mismatch", "RA derece birimiyle yazılmış ama birim saat seçili.")
        if suffix_hours or (unit == "hour" and not suffix_deg):
            if not (0.0 <= value <= 24.0):
                raise CoordinateError("ra_out_of_range", "RA saat olarak 0–24 aralığında olmalı.")
            deg = value * 15.0
        else:
            if unit == "auto" and not suffix_deg:
                notes.append("ra_assumed_degrees")
            deg = value
    if not (-360.0 <= deg <= 720.0):
        raise CoordinateError("ra_out_of_range", "RA derece olarak 0–360 aralığında olmalı.")
    wrapped = deg % 360.0
    if wrapped != deg:
        notes.append("ra_wrapped")
    return wrapped, tuple(notes)


def parse_dec(text: object) -> float:
    """Dec'i dereceye çevirir; [-90, +90] dışı reddedilir."""
    s = _clean(text)
    sex = _sexagesimal(s)
    if sex is not None:
        value, hint, neg = sex
        if hint == "h":
            raise CoordinateError("unit_mismatch", "Dec saat biriminde olamaz.")
        deg = -value if neg else value
    else:
        m = _PLAIN.match(s)
        if not m:
            raise CoordinateError("not_a_number", "Dec anlaşılamadı.")
        if (m["u"] or "").lower().startswith("h"):
            raise CoordinateError("unit_mismatch", "Dec saat biriminde olamaz.")
        deg = float(m["v"])
    if not math.isfinite(deg):
        raise CoordinateError("not_finite", "Dec sonlu bir sayı olmalı.")
    if not (-90.0 <= deg <= 90.0):
        raise CoordinateError("dec_out_of_range", "Dec −90 ile +90 derece arasında olmalı.")
    return deg


def parse_position(ra: object, dec: object, ra_unit: str = "auto") -> SkyPosition:
    ra_deg, notes = parse_ra(ra, ra_unit)
    return SkyPosition(ra_deg=ra_deg, dec_deg=parse_dec(dec), notes=notes)


def format_ra_hms(ra_deg: float, precision: int = 2) -> str:
    total = (ra_deg % 360.0) / 15.0 * 3600.0
    total = round(total, precision)
    if total >= 86400.0:
        total -= 86400.0
    h = int(total // 3600)
    m = int((total - h * 3600) // 60)
    s = total - h * 3600 - m * 60
    return f"{h:02d}h{m:02d}m{s:0{3 + precision}.{precision}f}s"


def format_dec_dms(dec_deg: float, precision: int = 1) -> str:
    sign = "-" if dec_deg < 0 else "+"
    total = round(abs(dec_deg) * 3600.0, precision)
    d = int(total // 3600)
    m = int((total - d * 3600) // 60)
    s = total - d * 3600 - m * 60
    return f"{sign}{d:02d}d{m:02d}m{s:0{3 + precision}.{precision}f}s"


def angular_separation_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Büyük çember ayrıklığı (Vincenty); küçük ve büyük açılarda kararlı."""
    l1, b1, l2, b2 = map(math.radians, (ra1, dec1, ra2, dec2))
    dl = l2 - l1
    num = math.hypot(math.cos(b2) * math.sin(dl), math.cos(b1) * math.sin(b2) - math.sin(b1) * math.cos(b2) * math.cos(dl))
    den = math.sin(b1) * math.sin(b2) + math.cos(b1) * math.cos(b2) * math.cos(dl)
    return math.degrees(math.atan2(num, den))
