"""Hat, işler, önbellek, API ve kalıcılık — SENTETİK arşivle (ağ erişimi yok)."""
import json
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from blinkspace import pipeline as pl
from blinkspace.analysis import Analysis
from blinkspace.api import create_app, parse_date
from blinkspace.db import Database
from blinkspace.jobs import JobManager
from blinkspace.pipeline import Cancelled, InsufficientData, SearchParams, mjd_to_iso

from conftest import TARGET, FakeExposure, add_matched_series, det_wcs

RA, DEC = TARGET


def wait(client, job, timeout=60.0):
    t0 = time.time()
    while job["status"] not in ("done", "insufficient_data", "failed", "cancelled"):
        assert time.time() - t0 < timeout, job
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job['id']}").json()["job"]
    return job


@pytest.fixture
def client(settings, pipeline):
    app = create_app(settings, pipeline)
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ hat
def test_end_to_end_sequence_from_synthetic_archive(pipeline, archive, settings):
    series = add_matched_series(archive, n=4)
    add_matched_series(archive, n=2, det_y=1600.0, rot0=3.0)        # uyumsuz dalga boyu: seçilmemeli
    stages = []
    res = pipeline.run(SearchParams(RA, DEC, 6.0), lambda s, p, d=None: stages.append(s))
    assert res["status"] == "done" and not res["reused"]
    assert [s for i, s in enumerate(stages) if i == 0 or stages[i - 1] != s] == ["searching", "downloading", "preparing", "done"]
    seq = pipeline.db.get_sequence(res["sequence_id"])
    m, frames = seq["meta"], seq["frames"]
    assert seq["status"] == "ready" and m["n_frames"] == 4 and m["n_visits"] == 4 and m["warnings"] == []
    assert [f["obs_id"] for f in frames] == [e.obs_id for e in series]                   # zaman sırası
    assert [f["mjd_avg"] for f in frames] == sorted(f["mjd_avg"] for f in frames)
    assert m["span_days"] == pytest.approx(360.0, abs=0.01)
    for f in frames:                                                                     # izlenebilirlik alanları
        for key in ("obs_id", "detector", "release", "l2_tag", "pipeline_version", "timesys", "mjd_avg", "date_avg", "lam_um",
                    "bw_um", "source_url", "archive_file_url", "raw_sha256", "quality", "background", "cutout_wcs"):
            assert f[key] not in (None, ""), key
        assert f["timesys"] == "UTC" and abs(f["dlam_over_bw"]) <= 0.5
        assert f["source_url"].startswith("https://irsa.ipac.caltech.edu/ibe/data/spherex/")
        assert f["background"]["value_mjy_sr"] == pytest.approx(0.4, abs=0.02)
        assert (settings.processed_dir / seq["id"] / f["png"]).is_file()
        raw = settings.raw_dir / f["raw_sha256"][:2] / f"{f['raw_sha256']}.fits"
        assert raw.is_file() and raw.stat().st_size == f["raw_size"]                     # ham dosya özetiyle saklanır
    al = m["alignment"]
    assert al["status"] == "ok" and al["rms_arcsec"] < 1.5 and al["n_measurements"] >= 8
    assert m["display"]["background_subtracted"] and m["wavelength"]["mode"] == "auto"
    px = [np.array(Image.open(settings.processed_dir / seq["id"] / f["png"])) for f in frames]
    assert all(p.shape == (59, 59, 2) for p in px)


def test_moving_source_moves_between_real_dates_in_aligned_frames(pipeline, archive, settings):
    add_matched_series(archive, n=3, step_days=365.25)
    seq = pipeline.db.get_sequence(pipeline.run(SearchParams(RA, DEC, 6.0))["sequence_id"])
    an = Analysis(settings, pipeline.db, pipeline)
    ys = []
    for i in range(3):
        fr = an._frame(seq, i)
        img = fr["image"] - float(fr["background"])
        c = img.shape[0] // 2
        sub = img[c - 6:c + 7, c - 3:c + 4]
        yy = np.mgrid[c - 6:c + 7, c - 3:c + 4][0]
        w = np.clip(np.nan_to_num(sub), 0, None)
        ys.append(float((w * yy).sum() / w.sum()))
    assert ys[1] - ys[0] == pytest.approx(10.0 / 6.15, abs=0.35) and ys[2] - ys[1] == pytest.approx(10.0 / 6.15, abs=0.35)


def test_same_request_reuses_sequence_and_archive_update_makes_a_new_one(pipeline, archive):
    add_matched_series(archive, n=3)
    p = SearchParams(RA, DEC, 6.0)
    first = pipeline.run(p)
    n_dl = archive.n_downloads
    again = pipeline.run(p)
    assert again["sequence_id"] == first["sequence_id"] and again["reused"] and archive.n_downloads == n_dl
    old = pipeline.db.get_sequence(first["sequence_id"])
    # arşiv güncellemesi: aynı gözlemin yeniden işlenmiş (QR3) kopyası + yeni bir gözlem
    e0 = archive.exposures[0]
    archive.add(FakeExposure(e0.obs_id, e0.detector, e0.mjd, e0.wcs, release="qr3", l2_version=27, proc=(2026, 271),
                             pipeline_version="7.0.5", collection="spherex_qr3"))
    archive.add(FakeExposure("2026W40_1A_0900_1", 2, 61300.0, det_wcs(RA, DEC, 600.0, 1000.0, 200.0)))
    pipeline.db._conn().execute("DELETE FROM tap_cache")                              # önbellek süresi dolmuş gibi
    new = pipeline.run(p)
    assert new["sequence_id"] != first["sequence_id"] and not new["reused"]
    seq = pipeline.db.get_sequence(new["sequence_id"])
    assert seq["meta"]["n_frames"] == 4 and seq["meta"]["selection"]["n_reprocessed_dropped"] == 1
    assert sum(f["obs_id"] == e0.obs_id for f in seq["frames"]) == 1                    # kopya ayrı zaman sayılmadı
    assert next(f for f in seq["frames"] if f["obs_id"] == e0.obs_id)["release"] == "qr3"
    assert pipeline.db.get_sequence(first["sequence_id"]) == old                        # eski dizi sessizce değişmedi
    assert seq["meta"]["data_fingerprint"] != old["meta"]["data_fingerprint"]


def test_cache_keys_do_not_mix_different_queries(pipeline, archive):
    add_matched_series(archive, n=3)
    add_matched_series(archive, n=3, det_y=1600.0, rot0=7.0)
    base = SearchParams(RA, DEC, 6.0)
    variants = [base, SearchParams(RA, DEC, 8.0), SearchParams(RA + 0.001, DEC, 6.0), SearchParams(RA, DEC, 6.0, max_frames=2),
                SearchParams(RA, DEC, 6.0, tol=0.25), SearchParams(RA, DEC, 6.0, mjd_min=61000.0),
                SearchParams(RA, DEC, 6.0, lam_um=2.0 + 1599.0 / 2039.0)]
    keys = [v.request_key() for v in variants]
    assert len(set(keys)) == len(keys)
    assert SearchParams(RA + 360.0, DEC, 6.0).request_key() == base.request_key()        # RA sarması aynı istek
    ids = [pipeline.run(v)["sequence_id"] for v in variants]
    assert len(set(ids)) == len(ids)
    by = {i: pipeline.db.get_sequence(i) for i in ids}
    assert by[ids[1]]["meta"]["grid"]["nx"] > by[ids[0]]["meta"]["grid"]["nx"]
    assert by[ids[3]]["meta"]["n_frames"] == 2
    assert by[ids[5]]["meta"]["mjd_first"] >= 61000.0
    assert by[ids[6]]["meta"]["wavelength"]["lam_ref_um"] == pytest.approx(2.784, abs=0.01)
    assert by[ids[6]]["meta"]["wavelength"]["mode"] == "requested"
    monkey_version = pl.PIPELINE_VERSION
    try:
        pl.PIPELINE_VERSION = "9.9.9"                                                   # işlem sürümü değişirse ayrı sonuç
        assert base.request_key() != keys[0]
    finally:
        pl.PIPELINE_VERSION = monkey_version


def test_insufficient_and_partial_data_paths(pipeline, archive):
    with pytest.raises(InsufficientData) as exc:
        pipeline.run(SearchParams(RA, DEC, 6.0))
    assert exc.value.reason == "no_coverage"
    archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(RA, DEC, 15.0, 1000.0, 0.0)))    # yalnızca kenarda
    pipeline.db._conn().execute("DELETE FROM tap_cache")
    with pytest.raises(InsufficientData) as exc:
        pipeline.run(SearchParams(RA, DEC, 6.0))
    assert exc.value.reason == "no_usable_frames"
    series = add_matched_series(archive, n=3)
    pipeline.db._conn().execute("DELETE FROM tap_cache")
    with pytest.raises(InsufficientData) as exc:
        pipeline.run(SearchParams(RA, DEC, 6.0, lam_um=4.9))
    assert exc.value.reason == "no_frames_at_wavelength" and exc.value.detail["groups"]
    series[1].fail_download = True                                                    # kısmi veri
    res = pipeline.run(SearchParams(RA, DEC, 6.0))
    seq = pipeline.db.get_sequence(res["sequence_id"])
    assert res["status"] == "done" and seq["meta"]["n_frames"] == 2 and "partial_data" in seq["meta"]["warnings"]
    assert seq["meta"]["selection"]["rejected_after_download"][0]["reason"] == "download_failed"
    series[0].fail_download = True                                                    # tek kare kaldı: yetersiz karşılaştırma
    # (farklı alan = farklı cutout adresi; önceki başarılı indirmeler ham depodan gelmesin)
    res = pipeline.run(SearchParams(RA, DEC, 7.0, max_frames=3))
    seq = pipeline.db.get_sequence(res["sequence_id"])
    assert res["status"] == "insufficient_data" and seq["status"] == "insufficient" and "single_frame" in seq["meta"]["warnings"]
    series[2].fail_download = True
    with pytest.raises(InsufficientData) as exc:
        pipeline.run(SearchParams(RA, DEC, 8.0, max_frames=4))
    assert exc.value.reason == "all_frames_rejected"


def test_single_visit_is_flagged_and_cancel_stops_the_run(pipeline, archive):
    for i in range(3):
        archive.add(FakeExposure(f"2025W20_1A_000{i}_1", 2, 60900.0 + 0.002 * i, det_wcs(RA, DEC, 700.0 + i, 1000.0, 5.0 * i)))
    seq = pipeline.db.get_sequence(pipeline.run(SearchParams(RA, DEC, 6.0))["sequence_id"])
    assert seq["status"] == "ready" and seq["meta"]["n_visits"] == 1 and "single_visit" in seq["meta"]["warnings"]
    with pytest.raises(Cancelled):
        pipeline.run(SearchParams(RA, DEC, 7.0), cancelled=lambda: True)


def test_mjd_iso_conversion_and_date_parsing():
    assert mjd_to_iso(60789.879611007) == "2025-04-24T21:06:38Z"
    assert mjd_to_iso(51544.5) == "2000-01-01T12:00:00Z"
    assert mjd_to_iso(60999.9999999) == "2025-11-21T00:00:00Z"
    assert parse_date("2025-04-24") == 60789.0 and parse_date("2025-04-24T21:06:38") == pytest.approx(60789.879606, abs=1e-5)
    assert parse_date("60789.5") == 60789.5 and parse_date("") is None and parse_date(None) is None
    for bad in ("2025-13-01", "2025-02-30", "yesterday", "12"):
        with pytest.raises(Exception):
            parse_date(bad)


# ------------------------------------------------------------------ işler
def test_job_lifecycle_merge_cache_and_cancel(settings, pipeline, archive):
    add_matched_series(archive, n=3)
    archive.download_delay = 0.25
    jm = JobManager(pipeline, pipeline.db, settings)
    try:
        p = SearchParams(RA, DEC, 6.0)
        j1 = jm.submit(p)
        j2 = jm.submit(p)
        assert j1["status"] in ("queued", "searching", "downloading") and j2["id"] == j1["id"] and j2.get("merged")   # aynı istek birleşir
        seen = set()
        t0 = time.time()
        while time.time() - t0 < 30:
            j = jm.get(j1["id"])
            seen.add(j["status"])
            if j["status"] == "done":
                break
            time.sleep(0.02)
        assert j["status"] == "done" and j["sequence_id"] and j["progress"] == 1.0
        assert "downloading" in seen                                                   # gerçek ara durum görüldü
        j3 = jm.submit(p)                                                              # önbellekten anında
        assert j3["status"] == "done" and j3["sequence_id"] == j["sequence_id"] and j3["detail"]["from_cache"]
        assert archive.n_tap == 1
        # iptal: çalışan iş
        jc = jm.submit(SearchParams(RA, DEC, 7.0))
        time.sleep(0.1)
        jm.cancel(jc["id"])
        t0 = time.time()
        while jm.get(jc["id"])["status"] not in ("cancelled", "done") and time.time() - t0 < 20:
            time.sleep(0.02)
        assert jm.get(jc["id"])["status"] == "cancelled" and jm.get(jc["id"])["sequence_id"] is None
        assert jm.cancel("nope") is None
        done = jm.cancel(j1["id"])                                                     # bitmiş iş iptal edilemez
        assert done["status"] == "done"
    finally:
        jm.stop()


def test_job_reports_archive_failure_and_insufficient_data(settings, pipeline, archive):
    jm = JobManager(pipeline, pipeline.db, settings)
    try:
        archive.tap_fail = 1
        j = jm.submit(SearchParams(RA, DEC, 6.0))
        while jm.get(j["id"])["status"] not in ("failed", "done", "insufficient_data"):
            time.sleep(0.02)
        j = jm.get(j["id"])
        assert j["status"] == "failed" and j["error"] == "archive_error"
        j = jm.submit(SearchParams(RA, DEC, 6.0))                                      # başarısız iş önbelleğe girmez
        while jm.get(j["id"])["status"] not in ("failed", "done", "insufficient_data"):
            time.sleep(0.02)
        j = jm.get(j["id"])
        assert j["status"] == "insufficient_data" and j["detail"]["reason"] == "no_coverage" and j["sequence_id"] is None
    finally:
        jm.stop()


# ------------------------------------------------------------------ API
def test_api_search_flow_and_sequence_payload(client, archive):
    add_matched_series(archive, n=3)
    r = client.post("/api/searches", json={"ra": "10h00m00s", "dec": "+20d00m00s", "fov_arcmin": 6, "max_frames": 3})
    assert r.status_code == 202
    body = r.json()
    assert body["position"]["ra_deg"] == pytest.approx(150.0) and body["position"]["ra_hms"] == "10h00m00.00s"
    job = wait(client, body["job"])
    assert job["status"] == "done"
    seq = client.get(f"/api/sequences/{job['sequence_id']}").json()
    assert len(seq["frames"]) == 3 and seq["meta"]["grid"]["orientation"] == "north_up_east_left"
    f0 = seq["frames"][0]
    assert "png" not in f0 and f0["image_url"].startswith("/api/sequences/")
    img = client.get(f0["image_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and "immutable" in img.headers["cache-control"]
    assert client.get(f0["mask_url"]).status_code == 200
    prov = client.get(f"/api/sequences/{seq['id']}/provenance").json()
    assert prov["frames"][0]["raw_sha256"] == f0["raw_sha256"] and "IRSA" in prov["citation"] and prov["archive"]["adql"]
    for bad in ("../../blinkspace.sqlite3", "sequence.json", "frame_00.npz", "frame_99.png"):
        assert client.get(f"/api/sequences/{seq['id']}/files/{bad}").status_code == 404
    assert client.get("/api/sequences/doesnotexist").status_code == 404
    assert client.get("/api/sequences/..%2F..").status_code == 404
    assert client.get("/api/jobs/unknownjob1").status_code == 404
    h = client.get("/api/health")
    assert h.json()["status"] == "ok" and h.headers["x-content-type-options"] == "nosniff" and "default-src 'self'" in h.headers["content-security-policy"]


@pytest.mark.parametrize("payload,code", [
    ({"ra": "abc", "dec": "5"}, "bad_coordinates"),
    ({"ra": "10", "dec": "95"}, "bad_coordinates"),
    ({"ra": "25:00:00", "dec": "5", "ra_unit": "hour"}, "bad_coordinates"),
    ({"ra": "10"}, "missing_coordinates"),
    ({"ra": "10", "dec": "5", "fov_arcmin": 500}, "bad_fov"),
    ({"ra": "10", "dec": "5", "fov_arcmin": 0.1}, "bad_fov"),
    ({"ra": "10", "dec": "5", "max_frames": 999}, "bad_max_frames"),
    ({"ra": "10", "dec": "5", "max_frames": 1}, "bad_max_frames"),
    ({"ra": "10", "dec": "5", "tol": 5}, "bad_tolerance"),
    ({"ra": "10", "dec": "5", "lam_um": 12.0}, "bad_wavelength"),
    ({"ra": "10", "dec": "5", "date_from": "2026-01-01", "date_to": "2025-01-01"}, "bad_date_range"),
    ({"ra": "10", "dec": "5", "date_from": "tomorrow"}, "bad_date"),
    ({"target_id": "pluto"}, "target_not_found"),
])
def test_api_rejects_bad_input(client, payload, code):
    r = client.post("/api/searches", json=payload)
    assert r.status_code in (404, 422) and r.json()["error"]["code"] == code
    assert client.get("/api/health").json()["active_jobs"] == 0                        # hatalı giriş iş başlatmaz


def test_api_rejects_non_finite_and_wrong_types(client):
    r = client.post("/api/searches", content='{"ra": "10", "dec": "5", "fov_arcmin": NaN}', headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request" and r.json()["error"]["fields"]
    assert client.post("/api/searches", json={"ra": [1, 2], "dec": "5"}).status_code == 422
    assert client.post("/api/searches", json={"ra": "10", "dec": "5", "ra_unit": "parsec"}).status_code == 422
    assert client.post("/api/searches", content="not json", headers={"content-type": "application/json"}).status_code == 422


def test_api_insufficient_data_and_cancel(client, archive):
    r = client.post("/api/searches", json={"ra": "150", "dec": "20"})
    job = wait(client, r.json()["job"])
    assert job["status"] == "insufficient_data" and job["detail"]["reason"] == "no_coverage"
    add_matched_series(archive, n=3)
    archive.download_delay = 0.4
    client.app.state.db._conn().execute("DELETE FROM tap_cache")
    job = client.post("/api/searches", json={"ra": "150", "dec": "20", "fov_arcmin": 5}).json()["job"]
    time.sleep(0.15)
    c = client.post(f"/api/jobs/{job['id']}/cancel")
    assert c.status_code == 200
    job = wait(client, c.json()["job"])
    assert job["status"] == "cancelled"
    assert client.post("/api/jobs/unknownjob1/cancel").status_code == 404


def make_sequence(client, archive, n=3):
    add_matched_series(archive, n=n)
    job = wait(client, client.post("/api/searches", json={"ra": "150", "dec": "20"}).json()["job"])
    return client.get(f"/api/sequences/{job['sequence_id']}").json()


def test_marks_are_sky_bound_and_shared_observation_roundtrip(client, archive):
    seq = make_sequence(client, archive)
    marks = [
        {"id": "m1", "classification": "possible_motion", "ra_deg": 150.0, "dec_deg": 19.9978, "frame_index": 0, "track_id": "t1", "note": "ilk konum"},
        {"id": "m2", "classification": "possible_motion", "ra_deg": 150.0, "dec_deg": 20.0033, "frame_index": 2, "track_id": "t1"},
        {"id": "m3", "kind": "region", "classification": "possible_brightness_change", "ra_deg": 149.9645, "dec_deg": 19.9944, "radius_arcsec": 15, "frame_index": 1},
    ]
    xss = "<script>alert(1)</script> & \"tırnak\""
    r = client.post("/api/observations", json={"sequence_id": seq["id"], "title": "Kuzeye kayan kaynak", "note": xss, "marks": marks,
                                               "view": {"zoom": 3, "frame": 2}})
    assert r.status_code == 201
    out = r.json()
    oid, token = out["observation"]["id"], out["edit_token"]
    assert out["share_path"] == f"/o/{oid}" and out["observation"]["status"] == "unverified_user_observation"
    got = client.get(f"/api/observations/{oid}").json()["observation"]
    assert got["note"] == xss                                                           # düz metin olarak saklanır, yorumlanmaz
    assert got["sequence"]["id"] == seq["id"] and got["sequence"]["frames"] == seq["frames"]   # aynı veri görüntüsü
    m1, m2, m3 = got["marks"]
    assert (m1["ra_deg"], m1["dec_deg"]) == (150.0, 19.9978) and m1["status"] == "unverified"
    assert m1["obs_id"] == seq["frames"][0]["obs_id"] and m2["obs_id"] == seq["frames"][2]["obs_id"]      # ilgili kare
    assert m1["mjd"] == seq["frames"][0]["mjd_avg"] and m2["date"] == seq["frames"][2]["date_avg"]       # gözlem zamanı
    assert m1["track_id"] == m2["track_id"] == "t1" and m1["mjd"] != m2["mjd"]                           # iz noktaları ayrı
    assert m3["kind"] == "region" and m3["radius_arcsec"] == 15 and got["view"] == {"zoom": 3, "frame": 2}
    assert "edit_token" not in json.dumps(got) and token not in json.dumps(got)
    # düzenleme ve silme yalnızca anahtarla
    upd = {"title": "güncel", "note": "n", "marks": marks[:1], "view": {}}
    assert client.put(f"/api/observations/{oid}", json=upd).status_code == 403
    assert client.put(f"/api/observations/{oid}", json=upd, headers={"X-Edit-Token": "wrong"}).status_code == 403
    ok = client.put(f"/api/observations/{oid}", json=upd, headers={"X-Edit-Token": token})
    assert ok.status_code == 200 and len(ok.json()["observation"]["marks"]) == 1 and ok.json()["observation"]["title"] == "güncel"
    assert client.delete(f"/api/observations/{oid}").status_code == 403
    assert client.delete(f"/api/observations/{oid}", headers={"X-Edit-Token": token}).status_code == 204
    assert client.get(f"/api/observations/{oid}").status_code == 404


@pytest.mark.parametrize("mark", [
    {"id": "a", "classification": "confirmed_planet", "ra_deg": 150, "dec_deg": 20, "frame_index": 0},   # keşif sınıfı yok
    {"id": "a", "classification": "unsure", "ra_deg": 400, "dec_deg": 20, "frame_index": 0},
    {"id": "a", "classification": "unsure", "ra_deg": 150, "dec_deg": -91, "frame_index": 0},
    {"id": "a", "classification": "unsure", "ra_deg": 150, "dec_deg": 20, "frame_index": 7},              # var olmayan kare
    {"id": "a b", "classification": "unsure", "ra_deg": 150, "dec_deg": 20, "frame_index": 0},
    {"id": "a", "kind": "region", "classification": "unsure", "ra_deg": 150, "dec_deg": 20, "frame_index": 0},   # yarıçapsız bölge
    {"id": "a", "classification": "unsure", "ra_deg": 150, "dec_deg": 20, "frame_index": 0, "note": "x" * 501},
])
def test_invalid_marks_are_rejected(client, archive, mark):
    seq = make_sequence(client, archive)
    r = client.post("/api/observations", json={"sequence_id": seq["id"], "marks": [mark]})
    assert r.status_code == 422


def test_observation_limits(client, archive):
    seq = make_sequence(client, archive)
    ok = {"id": "a", "classification": "unsure", "ra_deg": 150, "dec_deg": 20, "frame_index": 0}
    assert client.post("/api/observations", json={"sequence_id": seq["id"], "marks": [ok, ok]}).status_code == 422      # yinelenen kimlik
    assert client.post("/api/observations", json={"sequence_id": seq["id"], "note": "x" * 2001}).status_code == 422
    assert client.post("/api/observations", json={"sequence_id": seq["id"], "view": {"blob": "x" * 3000}}).status_code == 422
    assert client.post("/api/observations", json={"sequence_id": "nosuchseq1"}).status_code == 404
    assert client.post("/api/observations", json={"sequence_id": seq["id"]}).status_code == 201


def test_persistence_across_server_restart(settings, pipeline, archive):
    add_matched_series(archive, n=3)
    app = create_app(settings, pipeline)
    with TestClient(app) as c:
        job = wait(c, c.post("/api/searches", json={"ra": "150", "dec": "20"}).json()["job"])
        seq = c.get(f"/api/sequences/{job['sequence_id']}").json()
        ob = c.post("/api/observations", json={"sequence_id": seq["id"], "title": "kalıcı", "marks": [
            {"id": "m1", "classification": "unsure", "ra_deg": 150.0, "dec_deg": 20.0, "frame_index": 1}]}).json()
        png = c.get(seq["frames"][0]["image_url"]).content
    # yarım kalmış bir işi taklit et, sonra "sunucuyu yeniden başlat"
    db = Database(settings.db_path)
    db.create_job("halfdonejob1", "k", "sequence", SearchParams(RA, DEC, 9.0).normalized())
    db.update_job("halfdonejob1", status="downloading", stage="downloading", progress=0.4)
    db.close()
    pipeline2 = pl.Pipeline(settings, Database(settings.db_path), pipeline.model, {})
    app2 = create_app(settings, pipeline2)
    with TestClient(app2) as c2:
        again = c2.get(f"/api/observations/{ob['observation']['id']}").json()["observation"]
        assert again["title"] == "kalıcı" and again["marks"] == ob["observation"]["marks"]
        assert again["sequence"] == ob["observation"]["sequence"]                       # tamamlanmış sonuç aynı
        assert c2.get(seq["frames"][0]["image_url"]).content == png
        j = c2.get("/api/jobs/halfdonejob1").json()["job"]
        assert j["status"] == "failed" and j["error"] == "interrupted_by_restart"       # gerçek durum
        n_dl = archive.n_downloads
        cached = wait(c2, c2.post("/api/searches", json={"ra": "150", "dec": "20"}).json()["job"])
        assert cached["sequence_id"] == seq["id"] and archive.n_downloads == n_dl       # yeniden başlatma sonrası önbellek
        upd = c2.put(f"/api/observations/{ob['observation']['id']}", json={"title": "x"}, headers={"X-Edit-Token": ob["edit_token"]})
        assert upd.status_code == 200


def test_analysis_endpoints_on_synthetic_sequence(client, archive):
    series = add_matched_series(archive, n=3, step_days=365.25)
    series[2].flux_scale["var"] = 2.0                                                  # SENTETİK parlaklık değişimi
    job = wait(client, client.post("/api/searches", json={"ra": "150", "dec": "20"}).json()["job"])
    sid = job["sequence_id"]
    d = client.get(f"/api/sequences/{sid}/diff", params={"a": 0, "b": 2}).json()
    assert d["dt_days"] == pytest.approx(730.5, abs=0.01) and "no_psf_matching" in d["caveats"] and d["valid_frac"] > 0.8
    assert client.get(d["image_url"]).status_code == 200
    assert client.get(f"/api/sequences/{sid}/diff", params={"a": 1, "b": 1}).status_code == 422
    assert client.get(f"/api/sequences/{sid}/diff", params={"a": 0, "b": 9}).status_code == 422
    st = client.get(f"/api/sequences/{sid}/stack").json()
    assert st["n_frames"] == 3 and "moving_sources_blur" in st["caveats"] and client.get(st["image_url"]).status_code == 200
    ca = client.get(f"/api/sequences/{sid}/candidates", params={"a": 0, "b": 2}).json()
    kinds = {c["classification"] for c in ca["candidates"]}
    assert ca["status"] == "review_aid_not_a_discovery" and "possible_motion" in kinds and "possible_brightness_change" in kinds
    mv = next(c for c in ca["candidates"] if c["classification"] == "possible_motion")
    assert mv["dec"] > mv["dec_from"] and abs(mv["ra"] - 150.0) < 0.002                # kuzeye hareket, doğru yerde
    r, dd, _ = archive.stars["var"]
    lc = client.get(f"/api/sequences/{sid}/lightcurve", params={"ra": r, "dec": dd}).json()
    flux = [p["flux_mjy"] for p in lc["points"]]
    assert all(p["valid"] for p in lc["points"]) and flux[2] / flux[0] == pytest.approx(2.0, rel=0.05) and flux[1] / flux[0] == pytest.approx(1.0, rel=0.05)
    assert [p["date"] for p in lc["points"]] == sorted(p["date"] for p in lc["points"]) and lc["time_standard"] == "UTC"
    assert client.get(f"/api/sequences/{sid}/lightcurve").status_code == 422
    assert client.get(f"/api/sequences/{sid}/lightcurve", params={"follow_target": True}).status_code == 422   # hazır hedef değil
    g = client.get(f"/api/sequences/{sid}/overlay", params={"catalog": "gaia"}).json()
    assert g["type"] == "catalog" and g["n"] == len(archive.stars) and g["catalog_epoch"] == 2016.0
    assert client.get(f"/api/sequences/{sid}/overlay", params={"catalog": "sdss"}).status_code == 422


def test_rate_limit_and_tutorials_and_targets(client):
    t = client.get("/api/targets").json()
    assert [x["id"] for x in t["targets"]] == ["barnard", "eps-indi-b", "wise-0855", "rw-aur", "r-dra"]
    assert all(x["ready_sequence_id"] is None and x["frame"] == "ICRS" and x["epoch_jyear"] == 2000.0 for x in t["targets"])
    assert isinstance(client.get("/api/tutorials").json()["tutorials"], list)
    codes = [client.post("/api/searches", json={"ra": "abc", "dec": "1"}).status_code for _ in range(14)]
    assert codes[:12] == [422] * 12 and codes[-1] == 429
    assert client.get("/api/unknown").status_code == 404


def test_resubmitting_after_cancel_starts_a_new_job_instead_of_joining_the_cancelled_one(settings, pipeline, archive):
    jm = JobManager(pipeline, pipeline.db, settings, autostart=False)      # no worker: jobs stay where we put them
    p = SearchParams(RA, DEC, 6.0)
    first = jm.submit(p)
    pipeline.db.update_job(first["id"], status="searching", stage="searching")     # as if the worker were in the archive
    assert jm.submit(p)["id"] == first["id"]                                        # joined while it is still wanted
    jm.cancel(first["id"])
    second = jm.submit(p)
    assert second["id"] != first["id"] and second["status"] == "queued"
    assert second["ahead"] == 1                                                     # the cancelled one is still finishing


def test_pipeline_keeps_cancel_alive_while_the_archive_is_queried(pipeline, monkeypatch):
    from blinkspace import archive as archive_module
    from blinkspace import pipeline as pl

    def query(*args, **kwargs):
        checkpoint, _ = archive_module._hooks.value
        checkpoint()            # what the SIA client does five times a second while it waits
        raise AssertionError("the checkpoint should have raised")

    monkeypatch.setattr(pl, "query_observations", query)
    with pytest.raises(pl.Cancelled):
        pipeline.run(SearchParams(RA + 1.0, DEC, 6.0), cancelled=lambda: True)


def test_archive_outage_opens_frames_fetched_earlier_for_the_same_request(settings, pipeline, archive, monkeypatch):
    add_matched_series(archive, n=3)
    jm = JobManager(pipeline, pipeline.db, settings)
    try:
        p = SearchParams(RA, DEC, 6.0)
        first = jm.submit(p)
        t0 = time.time()
        while jm.get(first["id"])["status"] not in ("done", "failed", "insufficient_data") and time.time() - t0 < 30:
            time.sleep(0.02)
        first = jm.get(first["id"])
        assert first["status"] == "done"
        from blinkspace.archive import ArchiveError

        def down(*args, **kwargs):
            raise ArchiveError("IRSA SIA spherex_dr1 failed: 502 Proxy Error")

        monkeypatch.setattr(pipeline, "observations", down)                   # the archive goes down
        again = jm.submit(p, force_refresh=True)
        t0 = time.time()
        while jm.get(again["id"])["status"] not in ("done", "failed", "insufficient_data") and time.time() - t0 < 30:
            time.sleep(0.02)
        again = jm.get(again["id"])
        assert again["status"] == "done" and again["sequence_id"] == first["sequence_id"]
        assert again["detail"]["stale"] is True and again["detail"]["fetched_at"] > 0
    finally:
        jm.stop()
