"""Dedektör başına dalga boyu modelini (WCS-WAVE tablolarını) gerçek arşiv dosyalarından üretir.

Kullanım:  python -m tools.build_wave_model [--ra 270.0 --dec 66.56]

Her dedektör için verilen konumu kapsayan **en yeni** gözlemden küçük bir cutout indirilir ve dosyanın
WCS-WAVE tablosu `blinkspace/resources/wave_model.json` içine yazılır. Yeni bir veri sürümü geldiğinde bu
betik yeniden çalıştırılır; model yalnızca indirme öncesi seçim içindir (kesin dalga boyu her zaman
indirilen dosyanın kendi tablosundan hesaplanır).
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import httpx

from blinkspace.archive import dedupe, query_observations
from blinkspace.config import load_settings
from blinkspace.cutouts import cutout_url, fetch_bytes
from blinkspace.spx import read_spx
from blinkspace.wavelength import WaveModel, edge_distance, predict_detector_pixel

OUT = Path(__file__).resolve().parents[1] / "blinkspace" / "resources" / "wave_model.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ra", type=float, default=270.0, help="tüm dedektörlerce sık gözlenen bir konum (varsayılan: KEK derin alanı)")
    ap.add_argument("--dec", type=float, default=66.56)
    args = ap.parse_args()
    s = load_settings()
    with httpx.Client(timeout=s.tap_timeout_s, follow_redirects=True) as client:
        obs, meta = query_observations(args.ra, args.dec, s.tap_url, s.tap_timeout_s, s.max_retries, client)
        kept, _ = dedupe(obs)
        print(f"TAP: {meta['rows']} satır, {len(kept)} tekil, {meta['elapsed_s']} s")
        tables, sources = {}, {}
        for det in range(1, 7):
            cands = [o for o in kept if o.detector == det
                     and edge_distance(*predict_detector_pixel(o.footprint, args.ra, args.dec)) > 60]
            if not cands:
                raise SystemExit(f"D{det} için uygun gözlem yok; başka bir --ra/--dec deneyin")
            newest = max(cands, key=lambda o: (o.rank, o.mjd_start))
            url = cutout_url(s.irsa_base, newest.uri, args.ra, args.dec, 0.02)
            frame = read_spx(fetch_bytes(url, client, s.http_timeout_s, s.max_retries))
            tables[det] = frame.wave_table
            sources[det] = {
                "obs_id": newest.obs_id, "release": newest.release, "l2_tag": newest.l2_tag,
                "pipeline_version": frame.pipeline_version, "archive_uri": newest.uri,
                "lam_min_um": round(float(frame.wave_table.values[..., 0].min()), 4),
                "lam_max_um": round(float(frame.wave_table.values[..., 0].max()), 4),
            }
            print(f"D{det}: {newest.obs_id} {newest.release} {newest.l2_tag} v{frame.pipeline_version} "
                  f"λ {sources[det]['lam_min_um']}–{sources[det]['lam_max_um']} µm, tablo {frame.wave_table.values.shape}")
    note = (f"SPHEREx WCS-WAVE tabloları; {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} tarihinde "
            f"IRSA'dan üretildi (konum {args.ra}, {args.dec}). Yalnızca indirme öncesi dalga boyu öngörüsü içindir.")
    WaveModel(tables, sources).save(OUT, note)
    print("yazıldı:", OUT)


if __name__ == "__main__":
    main()
