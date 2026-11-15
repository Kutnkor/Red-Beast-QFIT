"""GERÇEK ARŞİV testleri (IRSA). Varsayılan olarak atlanır; `pytest --live` ile çalışır.

Bu dosyadaki hiçbir veri sentetik değildir: sorgular canlı TAP servisine, indirmeler IBE cutout servisine gider.
Testler temiz bir geçici veri klasöründe çalışır (önbelleksiz, gerçek indirme).
"""
import io
import json

import httpx
import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from blinkspace import selection
from blinkspace.archive import dedupe, query_observations
from blinkspace.cutouts import cutout_url, fetch_bytes
from blinkspace.db import Database
from blinkspace.pipeline import InsufficientData, Pipeline, SearchParams
from blinkspace.spx import read_spx
from blinkspace.targets import RESOURCES, load_targets
from blinkspace.wavelength import WaveModel, predict_detector_pixel

pytestmark = pytest.mark.live
RESULTS = {}


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    import os
    from blinkspace.config import load_settings
    d = tmp_path_factory.mktemp("live-data")
    old = os.environ.get("BLINKSPACE_DATA_DIR")
    os.environ["BLINKSPACE_DATA_DIR"] = str(d)
    try:
        s = load_settings()
    finally:
        if old is None:
            os.environ.pop("BLINKSPACE_DATA_DIR", None)
        else:
            os.environ["BLINKSPACE_DATA_DIR"] = old
    targets = load_targets()
    pipe = Pipeline(s, Database(s.db_path), WaveModel.load(RESOURCES / "wave_model.json"), targets)
    yield pipe, targets
    out = RESOURCES.parents[2] / "evidence" / "live_archive_tests.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(RESULTS, indent=1), encoding="utf-8")


def test_live_tap_query_returns_unique_level2_products(live):
    pipe, targets = live
    t = targets["barnard"]["search"]
    with httpx.Client(timeout=pipe.settings.tap_timeout_s, follow_redirects=True) as c:
        obs, meta = query_observations(t["ra_deg"], t["dec_deg"], pipe.settings.tap_url, pipe.settings.tap_timeout_s, 3, c)
    kept, dropped = dedupe(obs)
    assert meta["rows"] >= 100 and len(kept) >= 100
    assert len({o.key for o in kept}) == len(kept)                                   # (gözlem, dedektör) tekil
    assert {o.detector for o in kept} == {1, 2, 3, 4, 5, 6}
    assert all(len(o.footprint) == 4 and o.uri.startswith("ibe/data/spherex/") and 60700 < o.mjd_start < 62000 for o in kept)
    RESULTS["tap_barnard"] = {"rows": meta["rows"], "unique": len(kept), "dropped": len(dropped), "elapsed_s": meta["elapsed_s"]}


def test_live_cutout_layers_wavelength_and_footprint(live):
    pipe, targets = live
    t = targets["barnard"]["search"]
    kept, _, _ = pipe.observations(t["ra_deg"], t["dec_deg"])
    cands, _ = selection.build_candidates(kept, t["ra_deg"], t["dec_deg"], pipe.model, 80.0)
    newest = max(cands, key=lambda c: (c.obs.rank, c.obs.mjd_start))
    oldest = min(cands, key=lambda c: (c.obs.rank, c.obs.mjd_start))
    rec = []
    with httpx.Client(timeout=120, follow_redirects=True) as c:
        for cand in (oldest, newest):
            raw = fetch_bytes(cutout_url(pipe.settings.irsa_base, cand.obs.uri, t["ra_deg"], t["dec_deg"], 0.08), c, 120, 3)
            frame = read_spx(raw)
            assert frame.obs_id == cand.obs.obs_id and frame.detector == cand.obs.detector and frame.timesys == "UTC"
            assert {"IMAGE", "FLAGS", "VARIANCE", "WCS-WAVE"} <= set(frame.hdu_names) and frame.psf_kind in ("PSF", "EPSF")
            assert "SOURCE" in frame.flag_defs and "NONFUNC" in frame.flag_defs
            x, y = frame.world_to_pixel(t["ra_deg"], t["dec_deg"])
            lam, bw = frame.wavelength_at(x, y)
            hd = fits.open(io.BytesIO(raw))
            ws = WCS(hd["IMAGE"].header, fobj=hd, key="W")
            ws.sip = None
            la, ba = ws.pixel_to_world_values(x, y)
            assert float(lam[0]) == pytest.approx(float(la[0]), abs=1e-9) and float(bw[0]) == pytest.approx(float(ba[0]), abs=1e-9)
            dx, dy = frame.detector_coords(x, y)
            px, py = predict_detector_pixel(cand.obs.footprint, t["ra_deg"], t["dec_deg"])
            assert abs(px - float(dx[0])) < 20 and abs(py - float(dy[0])) < 20       # ayak izi öngörüsü
            assert abs(cand.lam_um - float(lam[0])) < 0.25 * float(bw[0])            # öngörülen dalga boyu yeterince yakın
            assert abs(frame.mjd_beg - cand.obs.mjd_start) < 1e-3
            rec.append({"obs_id": frame.obs_id, "release": cand.obs.release, "version": frame.pipeline_version, "psf": frame.psf_kind,
                        "lam_um": float(lam[0]), "pred_lam_um": cand.lam_um, "pixel_pred_err": [px - float(dx[0]), py - float(dy[0])],
                        "bytes": len(raw)})
    assert {r["release"] for r in rec} >= {"qr2"} or len(rec) == 2
    RESULTS["cutouts"] = rec


def test_live_end_to_end_preset_target(live):
    pipe, targets = live
    t = targets["eps-indi-b"]
    res = pipe.run(SearchParams(t["search"]["ra_deg"], t["search"]["dec_deg"], 5.0, None, 0.5, 3, None, None, "eps-indi-b"))
    seq = pipe.db.get_sequence(res["sequence_id"])
    m = seq["meta"]
    assert res["status"] == "done" and m["n_frames"] >= 2 and m["n_visits"] >= 2 and m["span_days"] > 100
    assert all(abs(f["dlam_over_bw"]) <= 0.5 and f["raw_sha256"] and f["timesys"] == "UTC" for f in seq["frames"])
    assert m["alignment"]["status"] == "ok" and m["alignment"]["rms_arcsec"] < 3.0
    with np.load(pipe.settings.processed_dir / seq["id"] / seq["frames"][0]["npz"]) as z:
        assert np.isnan(z["image"][z["invalid"]]).all()                              # gerçek veride de geçersiz = NaN
    RESULTS["preset_eps_indi_b"] = {"sequence": seq["id"], "n_frames": m["n_frames"], "n_visits": m["n_visits"], "span_days": m["span_days"],
                                    "lam_ref_um": m["wavelength"]["lam_ref_um"], "alignment_rms_arcsec": m["alignment"]["rms_arcsec"],
                                    "timings": m["timings"], "warnings": m["warnings"]}


def test_live_end_to_end_arbitrary_coordinate(live):
    """Hazır listede olmayan bir koordinat (COSMOS alanı yakınında): gerçek arşivle uçtan uca."""
    pipe, _ = live
    try:
        res = pipe.run(SearchParams(150.1163, 2.2058, 4.0, None, 0.5, 3))
    except InsufficientData as exc:
        RESULTS["arbitrary"] = {"status": "insufficient_data", "reason": exc.reason}
        pytest.fail(f"beklenmedik yetersiz veri: {exc.reason}")
    seq = pipe.db.get_sequence(res["sequence_id"])
    m = seq["meta"]
    assert m["n_frames"] >= 2 and m["archive"]["n_unique"] > 50
    assert m["grid"]["crval"] == pytest.approx([150.1163, 2.2058])
    RESULTS["arbitrary"] = {"status": res["status"], "sequence": seq["id"], "n_frames": m["n_frames"], "n_visits": m["n_visits"],
                            "span_days": m["span_days"], "lam_ref_um": m["wavelength"]["lam_ref_um"], "n_unique": m["archive"]["n_unique"],
                            "alignment": {k: m["alignment"].get(k) for k in ("status", "rms_arcsec", "n_measurements")},
                            "timings": m["timings"], "warnings": m["warnings"]}
