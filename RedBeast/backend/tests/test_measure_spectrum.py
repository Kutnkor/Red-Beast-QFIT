"""Hedef ölçümü (hareket/parlaklık durum basamakları) ve spektrum — SENTETİK arşivle."""
import math
import time

import pytest
from fastapi.testclient import TestClient

from blinkspace.analysis import Analysis
from blinkspace.api import create_app
from blinkspace.measure import measure_target
from blinkspace.pipeline import InsufficientData, SearchParams
from blinkspace.spectrum import SpectrumParams, choose_window, load_spectrum, pick_spread, run_spectrum

from conftest import TARGET, FakeExposure, add_matched_series, det_wcs

RA, DEC = TARGET


def target_record(archive):
    r0, d0, pr, pd, _, t0 = archive.mover
    # mover: mjd0'da (r0, d0); özdevinim derece/gün -> mas/yıl; katalog dönemi J2000'e geri taşınır
    yrs = (t0 - 51544.5) / 365.25
    pm_dec = pd * 365.25 * 3.6e6
    return {"ra_deg": r0, "dec_deg": d0 - pm_dec * yrs / 3.6e6, "pmra_masyr": 0.0, "pmdec_masyr": pm_dec, "epoch_jyear": 2000.0}


def test_motion_is_measured_and_compared_with_catalog(pipeline, archive, settings):
    add_matched_series(archive, n=4, step_days=180.0)
    pipeline.targets["mover"] = target_record(archive)
    seq = pipeline.db.get_sequence(pipeline.run(SearchParams(RA, DEC, 6.0, target_id="mover"))["sequence_id"])
    assert all("target_predicted" in f for f in seq["frames"])
    m = measure_target(Analysis(settings, pipeline.db, pipeline), seq, pipeline.targets["mover"])
    assert m["status"] == {"data_available": True, "source_detected": True, "change_seen": True, "change_kind": "motion",
                           "change_scientifically_confirmed": False}                 # doğrulama asla iddia edilmez
    mo = m["motion"]
    assert mo["n_points"] == 4 and mo["significant"] and mo["consistent_with_catalog"]
    assert mo["fit_pm_n_arcsec_yr"] == pytest.approx(10.0, abs=1.0) and abs(mo["fit_pm_e_arcsec_yr"]) < 1.0
    assert mo["catalog_pm_n_arcsec_yr"] == pytest.approx(10.0, abs=0.05)
    assert all(r["method"] == "flux_weighted_centroid" and r["snr"] > 20 for r in m["frames"])
    assert all(abs(r["offset_n_arcsec"]) < 2.0 for r in m["frames"])                  # öngörülen konumda bulundu
    # hareket eden kaynak için parlaklık değişimi iddia edilmez
    assert m["brightness"] is None or m["brightness"]["max_over_min"] < 1.2


def test_static_field_reports_no_change_and_brightness_needs_comparison_stars(pipeline, archive, settings):
    series = add_matched_series(archive, n=3, step_days=180.0)
    r, d, _ = archive.stars["var"]
    pipeline.targets["var"] = {"ra_deg": r, "dec_deg": d, "pmra_masyr": 0.0, "pmdec_masyr": 0.0, "epoch_jyear": 2000.0}
    an = Analysis(settings, pipeline.db, pipeline)
    seq = pipeline.db.get_sequence(pipeline.run(SearchParams(r, d, 6.0, target_id="var"))["sequence_id"])
    m = measure_target(an, seq, pipeline.targets["var"])
    assert m["status"]["source_detected"] and not m["status"]["change_seen"]
    assert m["motion"] is None or not m["motion"]["significant"]
    assert m["comparison"]["status"] == "ok" and m["comparison"]["n_stars"] >= 3
    assert m["brightness"]["normalized_by_comparison_stars"] and m["brightness"]["max_over_min"] < 1.1
    # SENTETİK parlaklık değişimi: son karede yıldız 2 kat parlak; karşılaştırma yıldızları sabit
    series[2].flux_scale["var"] = 2.0
    pipeline.db._conn().execute("DELETE FROM raw_files")
    seq2 = pipeline.db.get_sequence(pipeline.run(SearchParams(r, d, 6.5, target_id="var"))["sequence_id"])
    m2 = measure_target(an, seq2, pipeline.targets["var"])
    assert m2["status"]["change_seen"] and m2["status"]["change_kind"] == "brightness"
    assert m2["brightness"]["max_over_min"] == pytest.approx(2.0, rel=0.06) and m2["brightness"]["diff_sigma"] >= 3.0
    assert not m2["status"]["change_scientifically_confirmed"]


def test_saturated_core_and_invalid_target_are_not_measured_as_flux(pipeline, archive, settings):
    series = add_matched_series(archive, n=3, step_days=180.0)
    r0, d0, pr, pd, _, t0 = archive.mover
    for e in series:                                              # hareketli kaynağın çekirdeğini doymuş yap (3×3 geçersiz + OVERFLOW)
        x, y = e.wcs.all_world2pix([r0 + pr * (e.mjd - t0)], [d0 + pd * (e.mjd - t0)], 0)
        ix, iy = int(round(x[0])), int(round(y[0]))
        e.bad_pixels = [(ix + dx, iy + dy, "NONFUNC") for dx in (-1, 0, 1) for dy in (-1, 0, 1)] + [(ix + 2, iy, "OVERFLOW")]
    pipeline.targets["mover"] = target_record(archive)
    seq = pipeline.db.get_sequence(pipeline.run(SearchParams(RA, DEC, 6.0, target_id="mover"))["sequence_id"])
    assert "center_saturated" in seq["meta"]["warnings"]
    m = measure_target(Analysis(settings, pipeline.db, pipeline), seq, pipeline.targets["mover"])
    assert all(r["method"] == "saturated_core_centroid" for r in m["frames"])
    assert all(r["photometry"]["flux_mjy"] is None and r["photometry"]["reason"] == "invalid_pixels_in_aperture" for r in m["frames"])
    assert m["brightness"] is None and m["forced_mean"] is None                       # doymuş kaynakta akı uydurulmaz
    assert m["status"]["source_detected"] and m["motion"]["per_point_error_source"].startswith("assumed 0.3 px")
    mo = m["motion"]                                                                  # tam piksel öbek merkezi: kaba ama yansız
    assert abs(mo["fit_pm_n_arcsec_yr"] - 10.0) <= 3.0 * mo["fit_pm_err_arcsec_yr"] and mo["consistent_with_catalog"]
    assert mo["fit_pm_err_arcsec_yr"] > 1.5                                           # belirsizlik dürüstçe büyük
    assert m["wing_proxy"]["status"] == "indicative_only_not_photometry"


# ------------------------------------------------------------------ spektrum
def add_scan(archive, n=8, t0=60900.0, det=2):
    """Hedefi dedektör boyunca farklı satırlara (farklı dalga boylarına) koyan, günlere yayılmış pozlamalar."""
    out = []
    for i in range(n):
        y = 200.0 + 220.0 * i
        out.append(archive.add(FakeExposure(f"2025W30_1A_{500 + len(archive.exposures):04d}_1", det, t0 + 0.4 * i,
                                            det_wcs(RA, DEC, 900.0, y, 12.0 * i))))
    return out


def test_spectrum_points_carry_time_wavelength_and_uncertainty(pipeline, archive, settings):
    scan = add_scan(archive, n=8)
    late = archive.add(FakeExposure("2026W10_1A_0999_1", 2, 61100.0, det_wcs(RA, DEC, 900.0, 800.0, 0.0)))     # pencere dışı
    r, d, f = archive.stars["s1"]
    res = run_spectrum(pipeline, SpectrumParams(r, d, None, 10.0, 24))
    sp = load_spectrum(settings, res["result_id"])
    assert res["status"] == "done" and sp["n_points"] == 8 and sp["simultaneous"] is False and "not_simultaneous" in sp["caveats"]
    assert late.obs_id not in {p["obs_id"] for p in sp["points"]}
    lam = [p["lam_um"] for p in sp["points"]]
    assert lam == sorted(lam) and lam[-1] - lam[0] > 0.6                              # dalga boyuna göre sıralı, geniş kapsam
    omega = (6.15 / 206264.806) ** 2
    expected = f * omega * 1e9 * (1 - math.exp(-(2.0 ** 2) / (2 * 0.8 ** 2)))
    for p in sp["points"]:
        assert p["valid"] and p["reliable"] and p["timesys"] == "UTC" and p["date"].endswith("Z") and p["bw_um"] > 0
        assert p["flux_mjy"] == pytest.approx(expected, rel=0.06) and 0 < p["err_mjy"] < 0.1 * p["flux_mjy"]
    assert sp["span_days"] == pytest.approx(2.8, abs=0.01) and sp["time_standard"] == "UTC"
    again = run_spectrum(pipeline, SpectrumParams(r, d, None, 10.0, 24))
    assert again["reused"] and again["result_id"] == res["result_id"]
    sub = load_spectrum(settings, run_spectrum(pipeline, SpectrumParams(r, d, None, 10.0, 4))["result_id"])
    assert sub["n_points"] == 4 and sub["points"][0]["lam_um"] == lam[0] and sub["points"][-1]["lam_um"] == lam[-1]
    rng = load_spectrum(settings, run_spectrum(pipeline, SpectrumParams(r, d, None, 10.0, 24, None, lam[2] - 0.01, lam[5] + 0.01))["result_id"])
    assert [p["lam_um"] for p in rng["points"]] == lam[2:6]
    with pytest.raises(InsufficientData) as exc:
        run_spectrum(pipeline, SpectrumParams(r, d, 61100.0, 5.0, 24))
    assert exc.value.reason == "too_few_exposures_in_window"


def test_spectrum_keeps_invalid_points_as_missing(pipeline, archive, settings):
    scan = add_scan(archive, n=5)
    r, d, _ = archive.stars["s1"]
    x, y = scan[1].wcs.all_world2pix([r], [d], 0)
    scan[1].bad_pixels = [(int(round(x[0])), int(round(y[0])), "NONFUNC")]
    x, y = scan[3].wcs.all_world2pix([r], [d], 0)
    scan[3].bad_pixels = [(int(round(x[0])), int(round(y[0])), "OVERFLOW")]
    sp = load_spectrum(settings, run_spectrum(pipeline, SpectrumParams(r, d, None, 10.0, 24))["result_id"])
    by = {p["obs_id"]: p for p in sp["points"]}
    assert by[scan[1].obs_id]["valid"] is False and by[scan[1].obs_id]["flux_mjy"] is None      # ölçüm yok, sıfır değil
    assert by[scan[3].obs_id]["valid"] and not by[scan[3].obs_id]["reliable"] and by[scan[3].obs_id]["saturated"]
    assert sp["n_reliable"] == 3


def test_window_and_spread_helpers(archive, wave_tables):
    from blinkspace import selection
    from blinkspace.wavelength import WaveModel
    add_scan(archive, n=6, t0=60900.0)
    add_scan(archive, n=3, t0=61000.0)
    cands, _ = selection.build_candidates([e.observation() for e in archive.exposures], RA, DEC, WaveModel(wave_tables), 20.0)
    t0, t1 = choose_window(cands, None, 5.0)
    assert t0 == pytest.approx(60900.0, abs=1e-3) and t1 == pytest.approx(60905.0, abs=1e-3)   # en yoğun pencere
    assert choose_window(cands, 61000.0, 4.0) == (60998.0, 61002.0)
    picked = pick_spread(cands, 3)
    lam = sorted(c.lam_um for c in cands)
    assert [c.lam_um for c in picked][0] == lam[0] and [c.lam_um for c in picked][-1] == lam[-1] and len(picked) == 3


def test_spectrum_api_job(settings, pipeline, archive):
    add_scan(archive, n=6)
    r, d, _ = archive.stars["s2"]
    with TestClient(create_app(settings, pipeline)) as c:
        resp = c.post("/api/spectra", json={"ra": str(r), "dec": str(d), "window_days": 10, "max_points": 12})
        assert resp.status_code == 202 and resp.json()["job"]["kind"] == "spectrum"
        job = resp.json()["job"]
        t0 = time.time()
        while job["status"] not in ("done", "insufficient_data", "failed", "cancelled") and time.time() - t0 < 60:
            time.sleep(0.05)
            job = c.get(f"/api/jobs/{job['id']}").json()["job"]
        assert job["status"] == "done" and job["result_id"]
        sp = c.get(f"/api/spectra/{job['result_id']}").json()
        assert sp["kind"] == "spectrum" and sp["n_points"] == 6 and sp["position_mode"] == "fixed_sky_position"
        cached = c.post("/api/spectra", json={"ra": str(r), "dec": str(d), "window_days": 10, "max_points": 12}).json()["job"]
        assert cached["status"] == "done" and cached["result_id"] == job["result_id"]
        assert c.get("/api/spectra/" + "0" * 32).status_code == 404 and c.get("/api/spectra/../x").status_code == 404
        assert c.post("/api/spectra", json={"ra": "x", "dec": "1"}).json()["error"]["code"] == "bad_coordinates"
        assert c.post("/api/spectra", json={"ra": "1", "dec": "1", "window_days": 500}).status_code == 422
        assert c.post("/api/spectra", json={"ra": "1", "dec": "1", "lam_min_um": 2.0, "lam_max_um": 1.0}).json()["error"]["code"] == "bad_wavelength"
