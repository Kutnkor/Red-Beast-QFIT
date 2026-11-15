"""Hazır hedef dizilerinde hedefi ölçer ve özetini yazdırır (rapor üretiminden önce hızlı bakış).

Kullanım:  python -m tools.measure_presets [--only barnard]
"""
from __future__ import annotations

import argparse

from blinkspace.analysis import Analysis
from blinkspace.config import load_settings
from blinkspace.db import Database
from blinkspace.measure import measure_target
from blinkspace.pipeline import Pipeline
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.wavelength import WaveModel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    s = load_settings()
    db = Database(s.db_path)
    targets = load_targets()
    pipe = Pipeline(s, db, WaveModel.load(RESOURCES / "wave_model.json"), targets)
    an = Analysis(s, db, pipe)
    only = {x for x in a.only.split(",") if x}
    for tid, sid in db.get_meta("preset_sequences", {}).items():
        if only and tid not in only:
            continue
        seq = db.get_sequence(sid)
        m = measure_target(an, seq, targets[tid])
        print(f"== {tid} {sid} λ={seq['meta']['wavelength']['lam_ref_um']} {m['status']} seçilen {m['n_detected']}/{m['n_frames']} doymuş {m['n_saturated']}")
        for r in m["frames"]:
            ph = r["photometry"]
            flux = "—" if ph["flux_mjy"] is None else f"{ph['flux_mjy']:.3f}±{ph['err_mjy']:.3f}"
            print(f"   {r['date'][:10]} {r['method']} ofset=({r['offset_e_arcsec']},{r['offset_n_arcsec']})″ S/N={r['snr']} akı={flux} mJy {ph['reason'] or ''}")
        mo = m["motion"]
        if mo:
            print(f"   hareket: uyum=({mo['fit_pm_e_arcsec_yr']},{mo['fit_pm_n_arcsec_yr']})±{mo['fit_pm_err_arcsec_yr']} ″/yıl; "
                  f"katalog=({mo['catalog_pm_e_arcsec_yr']},{mo['catalog_pm_n_arcsec_yr']}); kayma={mo['measured_shift_px']} px; "
                  f"anlamlılık={mo['significance_sigma']}σ; katalogdan sapma={mo['residual_vs_catalog_sigma']}σ; n={mo['n_points']}")
        b = m["brightness"]
        if b:
            print(f"   parlaklık: {b['flux_min_mjy']}–{b['flux_max_mjy']} mJy, oran={b['max_over_min']}, fark={b['diff_sigma']}σ, n={b['n_points']}, "
                  f"tolerans={b['wavelength_tolerance_used']}, sistematik={b['systematic_frac']}, topluluk={b['normalized_by_comparison_stars']}")
        if m.get("forced_mean"):
            print(f"   zorlanmış ortalama: {m['forced_mean']['flux_mjy']}±{m['forced_mean']['err_mjy']} mJy (S/N {m['forced_mean']['snr']})")
        if m.get("wing_proxy"):
            w = m["wing_proxy"]
            print(f"   kanat göstergesi: kullanılabilir {w['n_usable']}, en büyük/en küçük={w.get('max_over_min')}")


if __name__ == "__main__":
    main()
