"""Zaman karşılaştırması için kare seçimi.

Kural: bir karşılaştırma kümesindeki tüm karelerin hedef konumundaki merkez dalga boyu, referans dalga
boyundan en fazla `tol × Δλ` uzakta olmalıdır (Δλ: referans dalga boyundaki bant genişliği, FWHM).
Aynı dedektör aynı dalga boyu demek değildir; seçim dedektöre değil dalga boyuna göre yapılır.

Tolerans gerekçesi: SPHEREx kanalları yaklaşık bir çözünürlük öğesi (Δλ = λ/R) aralıklıdır. tol = 0.5
iken iki geçirgenlik eğrisinin merkezleri en çok yarım FWHM ayrıdır (görsel karşılaştırma için yeterli
örtüşme). Nicel parlaklık karşılaştırması için tol = 0.25 kullanılır; kalan fark, kaynağın tayf eğimi
kadar sistematik hata bırakır ve raporlanır.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .archive import Observation
from .wavelength import WaveModel, edge_distance, predict_detector_pixel

VISIT_GAP_DAYS = 0.5  # bundan uzun zaman boşluğu ayrı "ziyaret" sayılır


@dataclass(frozen=True)
class Candidate:
    obs: Observation
    det_x: float          # öngörülen 1-tabanlı dedektör pikseli
    det_y: float
    lam_um: float         # öngörülen merkez dalga boyu
    bw_um: float          # öngörülen bant genişliği (FWHM)
    edge_px: float        # dedektör kenarına uzaklık


@dataclass
class WavelengthGroup:
    lam_ref_um: float
    bw_ref_um: float
    tol: float
    members: list[Candidate] = field(default_factory=list)

    @property
    def mjd_span(self) -> float:
        t = [c.obs.mjd_start for c in self.members]
        return (max(t) - min(t)) if t else 0.0

    @property
    def visits(self) -> list[list[Candidate]]:
        return split_visits(self.members)

    @property
    def detectors(self) -> list[int]:
        return sorted({c.obs.detector for c in self.members})

    def summary(self) -> dict:
        t = sorted(c.obs.mjd_start for c in self.members)
        return {
            "lam_ref_um": round(self.lam_ref_um, 5),
            "bw_ref_um": round(self.bw_ref_um, 5),
            "tol": self.tol,
            "n_frames": len(self.members),
            "n_visits": len(self.visits),
            "mjd_first": t[0] if t else None,
            "mjd_last": t[-1] if t else None,
            "span_days": round(self.mjd_span, 3),
            "detectors": self.detectors,
        }


def build_candidates(
    observations: list[Observation],
    ra_deg: float,
    dec_deg: float,
    model: WaveModel,
    min_edge_px: float,
) -> tuple[list[Candidate], list[dict]]:
    """Her gözlem için hedefin dedektör pikselini ve dalga boyunu öngörür.

    `min_edge_px`: hedef dedektör kenarına bundan yakınsa kare elenir (cutout kırpılır, alan eksik kalır).
    Döner: (adaylar, elenenlerin nedenleri).
    """
    out: list[Candidate] = []
    rejected: list[dict] = []
    for o in observations:
        if o.detector not in model.tables:
            rejected.append({"obs_id": o.obs_id, "detector": o.detector, "reason": "no_wave_model"})
            continue
        x, y = predict_detector_pixel(o.footprint, ra_deg, dec_deg)
        edge = edge_distance(x, y)
        if edge < min_edge_px:
            rejected.append({"obs_id": o.obs_id, "detector": o.detector, "reason": "near_detector_edge", "edge_px": round(edge, 1)})
            continue
        lam, bw = model.evaluate(o.detector, x, y)
        lam, bw = float(lam), float(bw)
        if not (math.isfinite(lam) and math.isfinite(bw) and bw > 0):
            rejected.append({"obs_id": o.obs_id, "detector": o.detector, "reason": "wavelength_undefined"})
            continue
        out.append(Candidate(o, x, y, lam, bw, edge))
    return out, rejected


def split_visits(cands: list[Candidate], gap_days: float = VISIT_GAP_DAYS) -> list[list[Candidate]]:
    """Zamana göre sıralayıp `gap_days`'ten uzun boşluklarda böler."""
    ordered = sorted(cands, key=lambda c: c.obs.mjd_start)
    visits: list[list[Candidate]] = []
    for c in ordered:
        if visits and c.obs.mjd_start - visits[-1][-1].obs.mjd_start <= gap_days:
            visits[-1].append(c)
        else:
            visits.append([c])
    return visits


def group_at(cands: list[Candidate], lam_ref_um: float, tol: float, bw_ref_um: float | None = None) -> WavelengthGroup:
    """Verilen referans dalga boyuna uyan adaylar. Δλ verilmezse en yakın adayın bant genişliği kullanılır."""
    if not cands:
        return WavelengthGroup(lam_ref_um, bw_ref_um or float("nan"), tol, [])
    if bw_ref_um is None:
        nearest = min(cands, key=lambda c: abs(c.lam_um - lam_ref_um))
        bw_ref_um = nearest.bw_um
    members = [c for c in cands if abs(c.lam_um - lam_ref_um) <= tol * bw_ref_um]
    return WavelengthGroup(lam_ref_um, bw_ref_um, tol, sorted(members, key=lambda c: c.obs.mjd_start))


def find_groups(cands: list[Candidate], tol: float, max_groups: int = 40) -> list[WavelengthGroup]:
    """Açgözlü, örtüşmeyen dalga boyu grupları; en iyi zaman kapsamına sahip olan önce.

    Puan: (ziyaret sayısı, zaman aralığı, kare sayısı). Her adımda en yüksek puanlı merkez seçilir,
    üyeleri havuzdan çıkarılır.
    """
    pool = list(cands)
    groups: list[WavelengthGroup] = []
    while pool and len(groups) < max_groups:
        lam = np.array([c.lam_um for c in pool])
        bw = np.array([c.bw_um for c in pool])
        t = np.array([c.obs.mjd_start for c in pool])
        order = np.argsort(lam)
        lam_s = lam[order]
        best_score, best_i = None, -1
        # aynı merkezlerin tekrar denenmemesi için benzersiz dalga boyları (1e-4 µm)
        seen: set[int] = set()
        for i in range(len(pool)):
            keyq = int(round(lam[i] * 1e4))
            if keyq in seen:
                continue
            seen.add(keyq)
            lo = np.searchsorted(lam_s, lam[i] - tol * bw[i], side="left")
            hi = np.searchsorted(lam_s, lam[i] + tol * bw[i], side="right")
            idx = order[lo:hi]
            tt = np.sort(t[idx])
            n_vis = 1 + int(np.sum(np.diff(tt) > VISIT_GAP_DAYS)) if len(tt) else 0
            score = (n_vis, float(tt[-1] - tt[0]) if len(tt) else 0.0, len(idx))
            if best_score is None or score > best_score:
                best_score, best_i = score, i
        center = pool[best_i]
        g = group_at(pool, center.lam_um, tol, center.bw_um)
        # referansı üyelerin ortancasına çek, toleransı yeniden uygula
        med = float(np.median([c.lam_um for c in g.members]))
        g2 = group_at(pool, med, tol, center.bw_um)
        if len(g2.members) >= len(g.members):
            g = g2
        groups.append(g)
        chosen = {id(c) for c in g.members}
        pool = [c for c in pool if id(c) not in chosen]
    groups.sort(key=lambda g: (len(g.visits), g.mjd_span, len(g.members)), reverse=True)
    return groups


def pick_frames(
    group: WavelengthGroup,
    max_frames: int,
    mjd_min: float | None = None,
    mjd_max: float | None = None,
) -> list[Candidate]:
    """Gruptan en çok `max_frames` kare seçer; zaman kapsamını korur.

    Önce her ziyaretten en iyi kare (dalga boyu sapması en küçük, sonra kenardan en uzak) alınır.
    Ziyaret sayısı sınırı aşıyorsa ilk ve son ziyaret korunarak eşit aralıklı alt küme seçilir.
    Yer kalırsa ziyaretlerin ikinci en iyi kareleri eklenir. Sonuç zaman sırasındadır.
    """
    members = [
        c for c in group.members
        if (mjd_min is None or c.obs.mjd_start >= mjd_min) and (mjd_max is None or c.obs.mjd_start <= mjd_max)
    ]
    if not members or max_frames < 1:
        return []

    def quality(c: Candidate):
        return (abs(c.lam_um - group.lam_ref_um), -c.edge_px)

    visits = [sorted(v, key=quality) for v in split_visits(members)]
    if len(visits) > max_frames:
        if max_frames == 1:
            idx = [0]
        else:
            idx = sorted({round(i * (len(visits) - 1) / (max_frames - 1)) for i in range(max_frames)})
        visits = [visits[i] for i in idx]
    chosen = [v[0] for v in visits]
    depth = 1
    while len(chosen) < max_frames:
        extra = [v[depth] for v in visits if len(v) > depth]
        if not extra:
            break
        room = max_frames - len(chosen)
        chosen.extend(extra[:room])
        depth += 1
    return sorted(chosen, key=lambda c: c.obs.mjd_start)
