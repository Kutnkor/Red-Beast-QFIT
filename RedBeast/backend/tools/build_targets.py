"""Beş zorunlu hedefin kimlik ve astrometri kayıtlarını SIMBAD'dan üretir.

Kullanım:  python -m tools.build_targets

Çıktı: `blinkspace/resources/targets.json`. Katalog değerleri SIMBAD TAP'tan (CfA yansısı) sorgu anında
alınır; açıklama ve gerekçe metinleri bu dosyada elle yazılmıştır.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

from blinkspace.archive import tap_sync_csv
from blinkspace.catalogs import propagate
from blinkspace.config import load_settings
from blinkspace.coords import angular_separation_deg, format_dec_dms, format_ra_hms, parse_position

OUT = Path(__file__).resolve().parents[1] / "blinkspace" / "resources" / "targets.json"
SEARCH_EPOCH = 2026.0  # SPHEREx verisinin (2025.3–2026.8) ortası

CURATED = [
    {
        "id": "barnard", "name": "Barnard's Star", "simbad_query": "Barnard's Star", "kind": "motion",
        "notes": {
            "tr": "Bilinen en büyük özdevinimli yıldız (~10.4″/yıl). SPHEREx pikseli 6.15″ olduğundan bir yılda yaklaşık 1.7 piksel kayar. Çok parlaktır (K≈4.5); çekirdek pikselleri doymuş olabilir.",
            "en": "Largest known proper motion of any star (~10.4″/yr). With 6.15″ SPHEREx pixels it shifts about 1.7 pixels per year. Very bright (K≈4.5); core pixels may be saturated.",
        },
    },
    {
        "id": "eps-indi-b", "name": "Epsilon Indi B", "simbad_query": "eps Ind B", "kind": "motion", "primary_query": "HD 209100",
        "notes": {
            "tr": "Eps Indi A'nın ~400″ uzağındaki kahverengi cüce çifti (Ba: T1, Bb: T6; ayrıklık ≈0.7″). SPHEREx çifti ayrı çözemez: tek, karışık bir kaynak beklenir. Ana yıldız Eps Indi A değildir.",
            "en": "Brown-dwarf binary (Ba: T1, Bb: T6; separation ≈0.7″) about 400″ from Eps Indi A. SPHEREx cannot resolve the pair: expect a single blended source. This is not the primary star Eps Indi A.",
        },
    },
    {
        "id": "wise-0855", "name": "WISE 0855−0714", "simbad_query": "WISE J085510.83-071442.5", "kind": "motion",
        "reference_coords": {"ra": "08h55m10.831s", "dec": "-7d14m42.53s"},
        "preferred_lam_um": 4.86,
        "preferred_lam_rationale": {
            "tr": "Y cücesi yalnızca ~4.5–5 µm'de parlaktır. Arşiv envanterinde 4.86 µm grubu en uzun zaman aralığına (3 ziyaret, ~368 gün) sahip uygun gruptur; otomatik seçim (2.34 µm) kaynağın görünmediği bir dalga boyuna düşer.",
            "en": "The Y dwarf is only bright near 4.5–5 µm. In the archive inventory the 4.86 µm group has the longest baseline among suitable groups (3 visits, ~368 days); the automatic choice (2.34 µm) lands where the source is invisible.",
        },
        "notes": {
            "tr": "Bilinen en soğuk kahverengi cüce (Y tipi), ~8.1″/yıl özdevinim. Yalnızca ~4.5–5 µm'de ve çok sönük (W2≈13.9) görünür; tek SPHEREx pozlamasında algılama sınırına yakındır. Sık kullanılan yayımlanmış koordinat WISE dönemine (~2010) aittir; 2026'da kaynak ~2′ batıdadır.",
            "en": "Coldest known brown dwarf (Y type), proper motion ~8.1″/yr. Visible only near 4.5–5 µm and very faint (W2≈13.9); close to the single-exposure SPHEREx detection limit. The commonly quoted published coordinate is from the WISE epoch (~2010); by 2026 the source is ~2′ further west.",
        },
    },
    {
        "id": "rw-aur", "name": "RW Aurigae", "simbad_query": "RW Aur", "kind": "variability",
        "preferred_lam_um": 0.765,
        "preferred_lam_rationale": {
            "tr": "Yıldız 0.85 µm'den uzun dalga boylarında doyma/doğrusalsızlık bayrağı taşıyor (otomatik seçilen 2.16 µm'de çekirdek doymuş). 0.765 µm grubunda üç ziyaretin tamamı bayraksız ve nicel ölçüme uygundur.",
            "en": "The star carries saturation/non-linearity flags longward of 0.85 µm (the automatically chosen 2.16 µm group has a saturated core). In the 0.765 µm group all three visits are flag-free and usable for quantitative measurement.",
        },
        "notes": {
            "tr": "Genç (T Tauri) değişen yıldız; A ve B bileşenleri ≈1.4″ ayrıktır ve SPHEREx'te tek kaynak olarak görünür. Düzensiz derin sönükleşmeleriyle bilinir.",
            "en": "Young (T Tauri) variable; components A and B are ≈1.4″ apart and appear as one source to SPHEREx. Known for irregular deep dimming events.",
        },
    },
    {
        "id": "r-dra", "name": "R Draconis", "simbad_query": "R Dra", "kind": "variability",
        "notes": {
            "tr": "Mira türü uzun dönemli değişen (dönem ≈245 gün). Kuzey ekliptik kutbuna ~9° uzaklıkta, SPHEREx derin alanında: yüzlerce tekrar gözlem var. Yakın kızılötesinde çok parlaktır; çekirdek pikselleri doymuştur.",
            "en": "Mira-type long-period variable (period ≈245 d). About 9° from the north ecliptic pole inside the SPHEREx deep field: hundreds of repeat observations. Very bright in the near-infrared; core pixels are saturated.",
        },
    },
]


def simbad(client, tap, name: str) -> dict:
    q = ("SELECT b.main_id, b.ra, b.dec, b.coo_err_maj, b.coo_bibcode, b.pmra, b.pmdec, b.pm_bibcode, "
         "b.plx_value, b.plx_bibcode, b.otype, b.sp_type FROM basic b JOIN ident i ON i.oidref = b.oid "
         "WHERE i.id = '{}'".format(name.replace("'", "''")))
    rows, _ = tap_sync_csv(tap, q, 60, 3, client)
    if len(rows) != 1:
        raise SystemExit(f"SIMBAD '{name}' için {len(rows)} kayıt döndürdü")
    r = rows[0]
    q2 = "SELECT i.id FROM ident i JOIN basic b ON i.oidref = b.oid WHERE b.main_id = '{}'".format(r["main_id"].replace("'", "''"))
    ids, _ = tap_sync_csv(tap, q2, 60, 3, client)
    return {"row": r, "ids": sorted(x["id"].strip() for x in ids)}


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> None:
    s = load_settings()
    targets = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for c in CURATED:
            res = simbad(client, s.simbad_tap_url, c["simbad_query"])
            r = res["row"]
            ra, dec = float(r["ra"]), float(r["dec"])
            pmra, pmdec = fnum(r["pmra"]), fnum(r["pmdec"])
            sra, sdec = propagate(ra, dec, pmra, pmdec, 2000.0, SEARCH_EPOCH)
            pm_tot = None if pmra is None else round((pmra ** 2 + pmdec ** 2) ** 0.5, 1)
            t = {
                "id": c["id"], "name": c["name"], "kind": c["kind"],
                "simbad_main_id": r["main_id"].strip(), "simbad_query": c["simbad_query"],
                "aliases": [i for i in res["ids"] if i.split(" ")[0] in ("GJ", "HD", "HIP", "Gaia", "2MASS", "WISE", "WISEA", "NAME", "V*", "*")][:12],
                "object_type": r["otype"].strip(), "spectral_type": r["sp_type"].strip(),
                "ra_deg": ra, "dec_deg": dec, "frame": "ICRS", "epoch_jyear": 2000.0,
                "ra_hms": format_ra_hms(ra), "dec_dms": format_dec_dms(dec),
                "coo_bibcode": r["coo_bibcode"].strip(),
                "pmra_masyr": pmra, "pmdec_masyr": pmdec, "pm_total_masyr": pm_tot, "pm_bibcode": r["pm_bibcode"].strip(),
                "parallax_mas": fnum(r["plx_value"]), "plx_bibcode": r["plx_bibcode"].strip(),
                "search": {
                    "ra_deg": round(sra, 6), "dec_deg": round(sdec, 6), "epoch_jyear": SEARCH_EPOCH, "fov_arcmin": 6.0,
                    "method": "J2000.0 katalog konumu, yalnızca özdevinimle J2026.0'a doğrusal ilerletildi (paralaks ve gözlemci etkisi yok)",
                    "shift_arcsec": round(angular_separation_deg(ra, dec, sra, sdec) * 3600.0, 1),
                    "rationale": {
                        "tr": "Alan, SPHEREx gözlem aralığının (2025.3–2026.8) ortasındaki öngörülen konuma merkezlenir; 6′ görüş alanı 1.5 yıllık hareketi ve karşılaştırma yıldızlarını içerir.",
                        "en": "The field is centred on the predicted position at the middle of the SPHEREx baseline (2025.3–2026.8); a 6′ field contains 1.5 years of motion plus comparison stars.",
                    },
                },
                "pixels_per_year": None if pm_tot is None else round(pm_tot / 1000.0 / 6.15, 2),
                "preferred_lam_um": c.get("preferred_lam_um"),
                "preferred_lam_rationale": c.get("preferred_lam_rationale"),
                "notes": c["notes"],
            }
            if "reference_coords" in c:
                p = parse_position(c["reference_coords"]["ra"], c["reference_coords"]["dec"])
                t["reference_coords"] = dict(c["reference_coords"], ra_deg=round(p.ra_deg, 6), dec_deg=round(p.dec_deg, 6),
                                             offset_from_search_center_arcsec=round(angular_separation_deg(p.ra_deg, p.dec_deg, sra, sdec) * 3600.0, 1),
                                             offset_from_j2000_arcsec=round(angular_separation_deg(p.ra_deg, p.dec_deg, ra, dec) * 3600.0, 1))
            if "primary_query" in c:
                pr = simbad(client, s.simbad_tap_url, c["primary_query"])["row"]
                t["primary_star"] = {
                    "simbad_main_id": pr["main_id"].strip(), "ra_deg": float(pr["ra"]), "dec_deg": float(pr["dec"]),
                    "separation_arcsec": round(angular_separation_deg(ra, dec, float(pr["ra"]), float(pr["dec"])) * 3600.0, 1),
                }
            targets.append(t)
            print(f"{t['name']}: {t['simbad_main_id']} J2000 {t['ra_hms']} {t['dec_dms']} pm=({pmra},{pmdec}) mas/yr "
                  f"→ J{SEARCH_EPOCH} ({sra:.5f}, {sdec:.5f}), kayma {t['search']['shift_arcsec']}″")
    doc = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"service": "SIMBAD TAP", "url": s.simbad_tap_url,
                   "note": "SIMBAD konumları ICRS, dönem J2000.0. WISE 0855 ve Barnard için özdevinim aritmetiğiyle doğrulandı."},
        "targets": targets,
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    print("yazıldı:", OUT)


if __name__ == "__main__":
    main()
