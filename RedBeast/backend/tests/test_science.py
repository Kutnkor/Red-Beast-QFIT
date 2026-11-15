"""Bilim modülleri — SENTETİK veriyle birim testleri (arşiv, dalga boyu, seçim, FITS, kalite, hizalama,
önizleme, fotometri, aday önerisi). Gerçek arşiv testleri `test_live_archive.py` içindedir."""
import io
import math
import struct

import httpx
import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from blinkspace import align, archive, preview, quality, selection
from blinkspace.analysis import detect_changes
from blinkspace.archive import ArchiveError, Observation, dedupe, parse_ewkb_polygon, parse_row, tap_sync_csv
from blinkspace.catalogs import mjd_to_jyear, propagate
from blinkspace.cutouts import CutoutError, cutout_url, fetch_bytes, validate_url
from blinkspace.photometry import aperture_photometry
from blinkspace.spx import SpxFormatError, parse_flag_defs, read_spx
from blinkspace.wavelength import WaveModel, WaveTable, edge_distance, predict_detector_pixel

from conftest import NDET, PIX, TARGET, FakeExposure, add_matched_series, det_wcs, linear_wave_table


# ------------------------------------------------------------------ arşiv
def ewkb(points, srid=True, little=True):
    e = "<" if little else ">"
    typ = 3 | (0x20000000 if srid else 0)
    out = (b"\x01" if little else b"\x00") + struct.pack(e + "I", typ)
    if srid:
        out += struct.pack(e + "I", 4326)
    out += struct.pack(e + "II", 1, len(points))
    for x, y in points:
        out += struct.pack(e + "dd", x, y)
    return out.hex().upper()


SQUARE = [(-93.1, 5.4), (-94.9, 5.1), (-94.6, 1.6), (-92.9, 1.9), (-93.1, 5.4)]


def row(obs="2025W33_2C_0321_1", det=6, rel="qr2", ver=20, yr=2025, doy=266, coll="spherex_qr2", t=60902.86):
    tag = f"l2b-v{ver}-{yr}-{doy:03d}"
    return {
        "obs_publisher_did": f"ivo://irsa.ipac/{coll}?{obs}/D{det}", "energy_bandpassname": f"SPHEREx-D{det}",
        "time_bounds_lower": str(t), "time_bounds_upper": str(t + 0.00133), "time_exposure": "113.5826",
        "provenance_version": "6.4", "poly": ewkb(SQUARE),
        "uri": f"ibe/data/spherex/{rel}/level2/{obs[:10]}/{tag}/{det}/level2_{obs}D{det}_spx_{tag}.fits",
        "contentchecksum": "md5:abc", "contentlength": "71634240",
    }


def test_ewkb_polygon_parsing_wraps_negative_longitude_and_drops_closing_point():
    for kw in ({}, {"srid": False}, {"little": False}):
        pts = parse_ewkb_polygon(ewkb(SQUARE, **kw))
        assert len(pts) == 4
        assert pts[0] == pytest.approx((266.9, 5.4))
    with pytest.raises(ValueError):
        parse_ewkb_polygon("0101000020E6100000")          # nokta, çokgen değil


def test_parse_row_extracts_identity_and_versions():
    o = parse_row(row())
    assert (o.obs_id, o.detector, o.collection, o.release, o.l2_tag) == ("2025W33_2C_0321_1", 6, "spherex_qr2", "qr2", "l2b-v20-2025-266")
    assert (o.l2_version, o.proc_year, o.proc_doy) == (20, 2025, 266) and len(o.footprint) == 4
    assert Observation.from_dict(o.to_dict()) == o
    assert parse_row(dict(row(), uri="ibe/data/spherex/qr2/cal/dark_D1.fits")) is None      # Level-2 görüntü değil
    assert parse_row(dict(row(), obs_publisher_did="ivo://irsa.ipac/spherex_qr2?X/D7")) is None
    bad = row()
    bad["uri"] = bad["uri"].replace("/6/", "/5/")                                           # dedektör uyuşmazlığı
    assert parse_row(bad) is None


def test_reprocessed_copies_are_one_observation_and_detectors_stay_separate():
    a = parse_row(row(rel="qr2", ver=20, doy=240))
    b = parse_row(row(rel="qr2", ver=25, yr=2026, doy=147))        # aynı gözlem, yeniden işlenmiş
    c = parse_row(row(rel="qr3", ver=27, yr=2026, doy=271, coll="spherex_qr3"))
    d5 = parse_row(row(det=5))                                      # aynı pozlama, farklı dedektör
    other = parse_row(row(obs="2026W10_1A_0001_2", t=61100.0))
    kept, dropped = dedupe([a, d5, b, other, c])
    assert len(kept) == 3 and len(dropped) == 2
    k6 = next(k for k in kept if k.key == ("2025W33_2C_0321_1", 6))
    assert k6.release == "qr3"                                      # en yeni sürüm tutulur
    assert {k.key for k in kept} == {("2025W33_2C_0321_1", 6), ("2025W33_2C_0321_1", 5), ("2026W10_1A_0001_2", 6)}
    assert [k.mjd_start for k in kept] == sorted(k.mjd_start for k in kept)   # zaman sırası
    assert dedupe([c, b, a])[0][0].release == "qr3"                 # sıra bağımsız


def test_tap_retries_transient_errors_then_gives_up():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text="a,b\n1,2\n")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows, meta = tap_sync_csv("https://tap.example/TAP", "SELECT 1", 5, 3, client, sleep=lambda s: None)
    assert rows == [{"a": "1", "b": "2"}] and meta["attempts"] == 3
    calls["n"] = -10
    with pytest.raises(ArchiveError):
        tap_sync_csv("https://tap.example/TAP", "SELECT 1", 5, 3, client, sleep=lambda s: None)
    assert calls["n"] == -7                                         # tam 3 deneme, sonsuz döngü yok

    def refused(request):
        raise httpx.ConnectError("no route")
    with pytest.raises(ArchiveError):
        tap_sync_csv("https://tap.example/TAP", "SELECT 1", 5, 2, httpx.Client(transport=httpx.MockTransport(refused)), sleep=lambda s: None)

    n400 = {"n": 0}

    def bad(request):
        n400["n"] += 1
        return httpx.Response(400, text="<VOTABLE>bad query</VOTABLE>")
    with pytest.raises(ArchiveError):
        tap_sync_csv("https://tap.example/TAP", "SELECT", 5, 3, httpx.Client(transport=httpx.MockTransport(bad)), sleep=lambda s: None)
    assert n400["n"] == 1                                           # kalıcı hata yeniden denenmez


def test_download_is_restricted_to_irsa_spherex_tree():
    url = cutout_url("https://irsa.ipac.caltech.edu/", "ibe/data/spherex/qr2/level2/x/l2b-v20-2025-240/6/f.fits", 361.5, -7.2, 0.1)
    assert url.endswith("?center=1.500000,-7.200000&size=0.10000")
    for bad in ("https://evil.example/ibe/data/spherex/x.fits", "http://irsa.ipac.caltech.edu/ibe/data/spherex/x.fits",
                "https://irsa.ipac.caltech.edu/other/x.fits", "https://user:pw@irsa.ipac.caltech.edu/ibe/data/spherex/x.fits",
                "https://irsa.ipac.caltech.edu:8443/ibe/data/spherex/x.fits", "file:///etc/passwd"):
        with pytest.raises(CutoutError):
            validate_url(bad)
    for uri in ("ibe/data/spherex/../../etc/passwd.fits", "ibe/data/wise/x.fits", "https://evil/x.fits", "ibe/data/spherex/a?b.fits"):
        with pytest.raises(CutoutError):
            cutout_url("https://irsa.ipac.caltech.edu/", uri, 1, 1, 0.1)
    with pytest.raises(CutoutError):
        cutout_url("https://irsa.ipac.caltech.edu/", "ibe/data/spherex/a.fits", 1, 1, 5.0)

    def html(request):
        return httpx.Response(200, text="<html>error</html>")
    with pytest.raises(CutoutError):
        fetch_bytes("https://irsa.ipac.caltech.edu/ibe/data/spherex/a.fits", httpx.Client(transport=httpx.MockTransport(html)), 5, 3, sleep=lambda s: None)


# ------------------------------------------------------------------ dalga boyu
def test_wave_table_bilinear_and_no_extrapolation():
    t = WaveTable(np.array([1.0, 11.0]), np.array([1.0, 21.0]), np.array([[[1.0, 0.1], [2.0, 0.2]], [[3.0, 0.3], [4.0, 0.4]]]))
    lam, bw = t.evaluate(6.0, 11.0)
    assert float(lam) == pytest.approx(2.5) and float(bw) == pytest.approx(0.25)
    assert float(t.evaluate(1.0, 1.0)[0]) == 1.0 and float(t.evaluate(11.0, 21.0)[0]) == 4.0
    lam, _ = t.evaluate(np.array([0.0, 12.0, 6.0, np.nan]), np.array([5.0, 5.0, 25.0, 5.0]))
    assert np.all(np.isnan(lam))                                    # tablo dışı: dışa değerleme yok
    with pytest.raises(ValueError):
        WaveTable(np.array([2.0, 1.0]), np.array([1.0, 2.0]), np.zeros((2, 2, 2)))


def test_wave_table_handles_repeated_control_points():
    # gerçek D3 tablosunda ardışık kontrol noktaları (140, 141) çok yakındır; sıfır aralık bölme hatası vermemeli
    t = WaveTable(np.array([1.0, 5.0, 5.0, 9.0]), np.array([1.0, 9.0]), np.dstack([np.tile([1.0, 2.0, 5.0, 6.0], (2, 1)), np.ones((2, 4))]))
    assert np.isfinite(t.evaluate(5.0, 3.0)[0])
    assert float(t.evaluate(3.0, 3.0)[0]) == pytest.approx(1.5)


def test_footprint_pixel_prediction_matches_wcs(wave_tables):
    for rot in (0.0, 37.0, 190.0, -75.0):
        for px, py in ((1020.0, 1020.0), (300.5, 1700.25), (1900.0, 120.0)):
            exp = FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(210.0, -35.0, px, py, rot))
            x, y = predict_detector_pixel(exp.observation().footprint, 210.0, -35.0)
            assert x == pytest.approx(px, abs=3.0) and y == pytest.approx(py, abs=3.0)
    exp = FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(0.02, 85.0, 500.0, 600.0, 20.0))   # RA=0 sarması + yüksek enlem
    x, y = predict_detector_pixel(exp.observation().footprint, 0.02, 85.0)
    assert x == pytest.approx(500.0, abs=4.0) and y == pytest.approx(600.0, abs=4.0)
    assert edge_distance(1.0, 500.0) == 0.0 and edge_distance(1020.0, 1020.0) == 1019.0 and edge_distance(-5.0, 10.0) < 0


def test_same_detector_does_not_mean_same_wavelength(wave_tables):
    model = WaveModel(wave_tables)
    a = FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 800.0, 400.0, 0.0)).observation()
    b = FakeExposure("2025W40_1A_0001_1", 2, 61000.0, det_wcs(*TARGET, 800.0, 1600.0, 0.0)).observation()
    cands, _ = selection.build_candidates([a, b], *TARGET, model, 50.0)
    assert cands[0].obs.detector == cands[1].obs.detector == 2
    assert abs(cands[0].lam_um - cands[1].lam_um) > 5 * cands[0].bw_um
    groups = selection.find_groups(cands, 0.5)
    assert len(groups) == 2 and all(len(g.members) == 1 for g in groups)       # aynı dedektör ama ayrı gruplar


# ------------------------------------------------------------------ seçim
def test_selection_groups_by_wavelength_and_keeps_time_order(archive, wave_tables):
    series = add_matched_series(archive, n=5, det=2, det_y=1000.0)
    add_matched_series(archive, n=2, det=2, det_y=1500.0, rot0=5.0)             # başka dalga boyu
    add_matched_series(archive, n=3, det=4, det_y=1000.0, rot0=80.0)            # başka dedektör, başka dalga boyu
    obs = [e.observation() for e in archive.exposures]
    cands, rejected = selection.build_candidates(obs, *TARGET, WaveModel(wave_tables), 60.0)
    assert len(cands) == 10 and rejected == []
    best = selection.find_groups(cands, 0.5)[0]
    assert len(best.members) == 5 and best.detectors == [2] and len(best.visits) == 5
    assert {c.obs.obs_id for c in best.members} == {e.obs_id for e in series}
    lam = [c.lam_um for c in best.members]
    assert max(lam) - min(lam) <= 0.5 * best.bw_ref_um
    picked = selection.pick_frames(best, 3)
    t = [c.obs.mjd_start for c in picked]
    assert len(picked) == 3 and t == sorted(t) and t[0] == series[0].mjd and t[-1] == series[-1].mjd   # uçlar korunur
    assert selection.pick_frames(best, 8, mjd_min=series[1].mjd, mjd_max=series[3].mjd + 1) == best.members[1:4]
    assert selection.pick_frames(best, 8, mjd_min=99999.0) == []
    req = selection.group_at(cands, cands[0].lam_um + 10.0, 0.5)
    assert req.members == []                                                    # istenen dalga boyunda kare yok


def test_selection_rejects_targets_near_detector_edge(archive, wave_tables):
    archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 12.0, 1000.0, 0.0)))
    archive.add(FakeExposure("2025W21_1A_0001_1", 2, 60950.0, det_wcs(*TARGET, 1000.0, 1000.0, 0.0)))
    cands, rejected = selection.build_candidates([e.observation() for e in archive.exposures], *TARGET, WaveModel(wave_tables), 60.0)
    assert len(cands) == 1 and rejected[0]["reason"] == "near_detector_edge"


def test_visits_split_on_time_gaps(archive, wave_tables):
    for i, dt in enumerate((0.0, 0.002, 0.004, 30.0, 30.001, 200.0)):
        archive.add(FakeExposure(f"2025W2{i}_1A_0001_1", 2, 60900.0 + dt, det_wcs(*TARGET, 700.0, 1000.0, 10.0 * i)))
    cands, _ = selection.build_candidates([e.observation() for e in archive.exposures], *TARGET, WaveModel(wave_tables), 60.0)
    g = selection.find_groups(cands, 0.5)[0]
    assert [len(v) for v in g.visits] == [3, 2, 1]
    picked = selection.pick_frames(g, 3)
    assert len({round(c.obs.mjd_start) for c in picked}) == 3                   # her ziyaretten bir kare
    assert len(selection.pick_frames(g, 5)) == 5 and len(selection.pick_frames(g, 16)) == 6


# ------------------------------------------------------------------ FITS okuma ve kalite
def test_reads_both_release_layouts_by_name(archive):
    e2 = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 700.0, 1000.0, 25.0)))
    e3 = archive.add(FakeExposure("2026W30_1A_0001_1", 2, 61250.0, det_wcs(*TARGET, 900.0, 1000.0, 70.0), release="qr3",
                                  l2_version=27, proc=(2026, 271), pipeline_version="7.0.5", collection="spherex_qr3"))
    f2 = read_spx(archive.render(e2, *TARGET, 0.1))
    f3 = read_spx(archive.render(e3, *TARGET, 0.1))
    assert f2.psf_kind == "PSF" and f3.psf_kind == "EPSF"                       # 5. katman sürüme göre değişir
    assert f2.flag_defs["SOURCE"] == 21 and f3.flag_defs["HALO"] == 28 and "PHANTOM" not in f3.flag_defs
    assert f2.timesys == "UTC" and f2.obs_id == e2.obs_id and f2.detector == 2 and f2.pipeline_version == "6.4"
    for f, e, py in ((f2, e2, 1000.0), (f3, e3, 1000.0)):
        x, y = f.world_to_pixel(*TARGET)
        dx, dy = f.detector_coords(x, y)
        assert float(dx[0]) == pytest.approx(e.wcs.wcs.crpix[0], abs=1e-3) and float(dy[0]) == pytest.approx(py, abs=1e-3)
        lam, bw = f.wavelength_at(x, y)
        assert float(lam[0]) == pytest.approx(2.0 + (py - 1) / (NDET - 1), abs=1e-6)        # dedektör 2: 2–3 µm sentetik
        assert float(lam[0] / bw[0]) == pytest.approx(40.0, rel=1e-5)


def test_layer_order_is_not_assumed_and_bad_files_are_rejected(archive):
    e = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 700.0, 1000.0, 0.0)))
    raw = archive.render(e, *TARGET, 0.05)
    hd = fits.open(io.BytesIO(raw))
    shuffled = fits.HDUList([hd[0], hd["WCS-WAVE"], hd["ZODI"], hd["VARIANCE"], hd["FLAGS"], hd["IMAGE"]])
    buf = io.BytesIO()
    shuffled.writeto(buf)
    f = read_spx(buf.getvalue())
    assert f.image.shape == f.flags.shape and f.psf_kind is None and np.array_equal(f.image, read_spx(raw).image)

    def broken(mutate):
        h = fits.open(io.BytesIO(raw))
        mutate(h)
        b = io.BytesIO()
        h.writeto(b)
        return b.getvalue()

    for mutate in (lambda h: h.pop(h.index_of("FLAGS")), lambda h: h["IMAGE"].header.__setitem__("BUNIT", "DN"),
                   lambda h: h["IMAGE"].header.__delitem__("MJD-BEG"), lambda h: h["IMAGE"].header.__delitem__("CRPIX1W"),
                   lambda h: [h["FLAGS"].header.__delitem__(k) for k in list(h["FLAGS"].header) if k.startswith("MP_")]):
        with pytest.raises(SpxFormatError):
            read_spx(broken(mutate))
    with pytest.raises(Exception):
        read_spx(b"not a fits file")


def test_flag_definitions_come_from_each_file_header():
    h = fits.Header()
    h["MP_HOT"] = 3
    h["MP_SOURCE"] = 9
    assert parse_flag_defs(h) == {"HOT": 3, "SOURCE": 9}
    h2 = fits.Header()
    h2["MSKN0003"] = "SOURCE"
    h2["MSKM0003"] = 8
    h2["MSKN0009"] = "HOT"
    assert parse_flag_defs(h2) == {"SOURCE": 3, "HOT": 9}                       # aynı ad, başka bit: sabit tablo varsayılmaz


def test_quality_masks_classify_flags_and_unknown_names_are_suspect(archive):
    e = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 700.0, 1000.0, 0.0),
                                 bad_pixels=[(700, 1000, "NONFUNC"), (702, 1000, "TRANSIENT"), (704, 1000, "SOURCE"), (706, 1000, "OVERFLOW")]))
    f = read_spx(archive.render(e, *TARGET, 0.05))
    f.flag_defs["BRAND_NEW_FLAG"] = 30
    x, y = (float(v[0]) for v in f.world_to_pixel(*TARGET))
    ix, iy = int(round(x)) + 1, int(round(y)) + 1          # bad_pixels 0-tabanlı dedektör; hedef 1-tabanlı (700, 1000)
    f.flags[iy, ix + 9] |= 1 << 30
    m = quality.flag_masks(f)
    assert m.invalid[iy, ix] and not m.suspect[iy, ix]                          # NONFUNC: ölçüm yok
    assert m.suspect[iy, ix + 2] and not m.invalid[iy, ix + 2]                  # TRANSIENT: şüpheli
    assert not m.suspect[iy, ix + 4] and not m.invalid[iy, ix + 4] and m.source[iy, ix + 4]   # SOURCE: yalnızca bilgi
    assert m.suspect[iy, ix + 9] and m.unknown_names == ("BRAND_NEW_FLAG",)     # tanınmayan ad temkinli
    q = quality.quality_summary(f, (x, y), radius_px=8.0)
    assert q["target"]["saturated"] and q["target"]["n_invalid"] == 1 and "SOURCE" in q["target"]["info_flags"]
    assert q["flags_present"]["NONFUNC"] == 1 and q["n_nonfinite"] == 1


# ------------------------------------------------------------------ hizalama
def render_aligned(archive, exp, fov=6.0):
    frame = read_spx(archive.render(exp, *TARGET, fov / 60.0 * 1.45 + 0.012))
    grid, shape = align.target_grid(*TARGET, fov)
    return frame, align.reproject_frame(frame, grid, shape), grid, shape


def star_centroid(archive, aligned, grid, name):
    r, d, _ = archive.stars[name]
    x0, y0 = grid.all_world2pix([r], [d], 0)
    c = align.centroid(aligned.image - np.nanmedian(aligned.image), float(x0[0]), float(y0[0]))
    return c[0] - float(x0[0]), c[1] - float(y0[0])


def test_grid_is_north_up_east_left_and_centred():
    grid, shape = align.target_grid(150.0, 20.0, 6.0)
    assert shape == (59, 59) and shape[0] % 2 == 1
    c = (shape[0] - 1) / 2
    ra, dec = grid.all_pix2world([c, c, c + 1], [c, c + 1, c], 0)
    assert ra[0] == pytest.approx(150.0) and dec[0] == pytest.approx(20.0)
    assert dec[1] - dec[0] == pytest.approx(PIX, rel=1e-6)                      # +y = kuzey
    assert (ra[2] - ra[0]) * math.cos(math.radians(20.0)) == pytest.approx(-PIX, rel=1e-4)   # +x = batı (doğu solda)
    d = align.grid_to_dict(grid, shape)
    assert d["nx"] == 59 and d["pixscale_arcsec"] == pytest.approx(6.15) and d["cdelt"][0] < 0 < d["cdelt"][1]


@pytest.mark.parametrize("rot", [0.0, 33.0, 90.0, 171.0, -120.0])
def test_alignment_recovers_known_star_positions_for_any_roll(archive, rot):
    exp = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 700.3, 999.6, rot)))
    _, al, grid, _ = render_aligned(archive, exp)
    for name in ("s1", "s2", "s3", "s4"):
        dx, dy = star_centroid(archive, al, grid, name)
        assert abs(dx) < 0.25 and abs(dy) < 0.25, (name, rot, dx, dy)          # piksel


def test_controlled_shift_is_measured_and_moving_source_is_not_pinned(archive):
    """Hareketli kaynak hizalamada sabitlenmez: sabit yıldızlar yerinde kalır, kaynak öngörülen kadar kayar."""
    e0 = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 700.0, 1000.0, 15.0)))
    e1 = archive.add(FakeExposure("2026W20_1A_0001_1", 2, 60900.0 + 730.5, det_wcs(*TARGET, 820.0, 1001.0, 140.0)))
    _, a0, grid, _ = render_aligned(archive, e0)
    _, a1, _, _ = render_aligned(archive, e1)
    for name in ("s1", "s2", "s3"):
        d0, d1 = star_centroid(archive, a0, grid, name), star_centroid(archive, a1, grid, name)
        assert abs(d0[0] - d1[0]) < 0.3 and abs(d0[1] - d1[1]) < 0.3
    r0, dec0, pr, pd, _, t0 = archive.mover
    pos = []
    for al, e in ((a0, e0), (a1, e1)):
        x, y = grid.all_world2pix([r0 + pr * (e.mjd - t0)], [dec0 + pd * (e.mjd - t0)], 0)
        c = align.centroid(al.image - np.nanmedian(al.image), float(x[0]), float(y[0]))
        pos.append((c[0], c[1]))
    shift_px = pos[1][1] - pos[0][1]
    assert shift_px == pytest.approx(20.0 / 6.15, abs=0.3)                       # 2 yıl × 10″/yıl kuzeye
    assert abs(pos[1][0] - pos[0][0]) < 0.3


def test_invalid_pixels_stay_missing_not_zero_and_flags_are_not_averaged(archive):
    exp = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 700.0, 1000.0, 30.0),
                                   bad_pixels=[(699, 999, "NONFUNC"), (690, 990, "TRANSIENT")]))
    frame, al, grid, shape = render_aligned(archive, exp)
    c = shape[0] // 2
    assert al.invalid[c, c] and np.isnan(al.image[c, c])                        # geçersiz piksel NaN kalır
    assert not np.any(al.image[al.invalid] == 0)                                # asla 0 ile doldurulmaz
    assert np.all(np.isnan(al.image[al.invalid]))
    assert 1 <= al.invalid.sum() <= 9                                           # temkinli ama sınırlı büyüme
    assert al.suspect.dtype == bool and 1 <= al.suspect.sum() <= 4 and not np.any(al.suspect & al.invalid)
    assert al.invalid.dtype == bool and al.coverage.all()
    assert np.nanmin(al.image) > 0.2                                            # arka plan ~0.4; sahte sıfır yok


def test_partial_coverage_is_masked(archive):
    exp = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 12.0, 1000.0, 0.0)))   # dedektör kenarı
    _, al, _, _ = render_aligned(archive, exp)
    assert 0.3 < al.coverage.mean() < 0.9
    assert np.all(al.invalid[~al.coverage]) and np.all(np.isnan(al.image[~al.coverage]))


def test_wavelength_map_and_comparable_mask(archive):
    exp = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 700.0, 1000.0, 0.0)))
    frame, al, grid, shape = render_aligned(archive, exp, fov=30.0)
    c = shape[0] // 2
    lam0 = float(al.lam_um[c, c])
    assert lam0 == pytest.approx(2.0 + 999.0 / (NDET - 1), abs=1e-4)
    grad = float(al.lam_um[c + 50, c] - al.lam_um[c - 50, c])
    assert abs(grad) == pytest.approx(100.0 / (NDET - 1), rel=0.02)             # eğim dedektör y'si boyunca
    bw = lam0 / 40.0
    wide = align.comparable_mask(al, lam0, bw, 0.5)
    narrow = align.comparable_mask(al, lam0, bw, 0.25)
    assert wide[c, c] and 0.3 < wide.mean() < 0.9 and narrow.sum() < wide.sum()  # merkez uyumlu, kenarlar değil
    assert not align.comparable_mask(al, lam0 + 5 * bw, bw, 0.5).any()


def test_robust_background_and_common_display_scale():
    rng = np.random.default_rng(1)
    img = 0.4 + rng.normal(0, 0.02, (60, 60))
    img[10:14, 10:14] += 50.0
    bkg, sig, n = align.robust_background(img, np.zeros(img.shape, bool))
    assert bkg == pytest.approx(0.4, abs=0.005) and sig == pytest.approx(0.02, rel=0.25) and n > 3000
    assert math.isnan(align.robust_background(img, np.ones(img.shape, bool))[0])
    a, b = img - bkg, (img - bkg) * 3.0
    lim = preview.display_limits([a, b], [sig, sig])
    sa, sb = preview.stretch(a, lim), preview.stretch(b, lim)
    assert sa.dtype == np.uint8 and sb[12, 12] >= sa[12, 12]
    ramp = preview.stretch(np.linspace(lim["vmin"], lim["vmax"], 50)[None, :], lim)[0]
    assert np.all(np.diff(ramp.astype(int)) >= 0) and ramp[0] == 0 and ramp[-1] == 255      # tekdüze, ortak ölçek
    assert preview.stretch(np.full((1, 1), 5 * sig), lim)[0, 0] == preview.stretch(np.full((2, 2), 5 * sig), lim)[0, 0]
    assert preview.stretch(np.array([[lim["vmin"], lim["vmax"], np.nan]]), lim).tolist() == [[0, 255, 0]]


def test_preview_png_is_north_up_and_invalid_is_transparent(tmp_path):
    img = np.zeros((5, 7), np.float32)
    img[4, 0] = 100.0                                                            # FITS'te en kuzey satır, en doğu sütun
    invalid = np.zeros((5, 7), bool)
    invalid[0, 6] = True
    img[0, 6] = np.nan
    lim = {"vmin": 0.0, "vmax": 100.0, "soft": 10.0, "sigma": 1.0}
    preview.write_gray_png(tmp_path / "f.png", img, invalid, lim)
    px = np.array(Image.open(tmp_path / "f.png"))
    assert px.shape == (5, 7, 2)
    assert px[0, 0, 0] == 255 and px[0, 0, 1] == 255                             # kuzey satırı PNG'nin ilk satırı
    assert px[4, 6, 1] == 0                                                      # geçersiz piksel saydam
    assert px[2, 3, 1] == 255 and px[2, 3, 0] == 0
    preview.write_diff_png(tmp_path / "d.png", np.array([[0.0, 1.0, -1.0, np.nan]]), np.array([[False, False, False, True]]), 1.0)
    d = np.array(Image.open(tmp_path / "d.png"))
    assert d[0, 0, 0] in (127, 128) and d[0, 1, 0] == 255 and d[0, 2, 0] == 0 and d[0, 3, 1] == 0


# ------------------------------------------------------------------ fotometri
def test_aperture_photometry_recovers_injected_flux_from_native_pixels(archive):
    exp = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, det_wcs(*TARGET, 700.0, 1000.0, 20.0)))
    frame = read_spx(archive.render(exp, *TARGET, 0.16))
    r, d, f = archive.stars["s1"]
    ph = aperture_photometry(frame, r, d)
    omega = (6.15 / 206264.806) ** 2
    expected_mjy = f * omega * 1e9 * (1 - math.exp(-(2.0 ** 2) / (2 * 0.8 ** 2)))    # r=2 px açıklık içindeki Gauss kesri
    assert ph["valid"] and ph["reliable"] and ph["flux_mjy"] == pytest.approx(expected_mjy, rel=0.04)
    assert 0 < ph["err_mjy"] < 0.05 * ph["flux_mjy"]
    assert ph["background_mjy_sr"] == pytest.approx(0.4, abs=0.02)
    empty = aperture_photometry(frame, TARGET[0] + 0.02, TARGET[1] + 0.03)
    assert empty["valid"] and abs(empty["flux_mjy"]) < 4 * empty["err_mjy"]            # boş gökyüzü ≈ 0 ± hata


def test_photometry_refuses_invalid_pixels_and_flags_saturation(archive):
    r, d, _ = archive.stars["s1"]
    w = det_wcs(*TARGET, 700.0, 1000.0, 0.0)
    sx, sy = w.all_world2pix([r], [d], 0)
    ix, iy = int(round(sx[0])), int(round(sy[0]))
    bad = archive.add(FakeExposure("2025W20_1A_0001_1", 2, 60900.0, w, bad_pixels=[(ix, iy, "NONFUNC")]))
    ph = aperture_photometry(read_spx(archive.render(bad, *TARGET, 0.16)), r, d)
    assert not ph["valid"] and ph["flux_mjy"] is None and ph["reason"] == "invalid_pixels_in_aperture"   # ölçüm yok ≠ 0
    sat = archive.add(FakeExposure("2025W21_1A_0001_1", 2, 60950.0, w, bad_pixels=[(ix, iy, "OVERFLOW")]))
    ph = aperture_photometry(read_spx(archive.render(sat, *TARGET, 0.16)), r, d)
    assert ph["valid"] and ph["saturated"] and not ph["reliable"] and ph["reason"] == "saturated_or_nonlinear"
    off = aperture_photometry(read_spx(archive.render(sat, *TARGET, 0.16)), TARGET[0] + 1.0, TARGET[1])
    assert not off["valid"] and off["reason"] == "off_frame"


def test_proper_motion_propagation():
    ra, dec = propagate(269.4520769586, 4.6933649666, -801.551, 10362.394, 2000.0, 2016.0)
    assert dec == pytest.approx(4.739420, abs=2e-5) and ra == pytest.approx(269.448502, abs=2e-5)    # Gaia DR3 J2016 konumu
    assert propagate(10.0, 20.0, None, None, 2000.0, 2026.0) == (10.0, 20.0)
    assert mjd_to_jyear(51544.5) == 2000.0 and mjd_to_jyear(51544.5 + 365.25) == 2001.0


# ------------------------------------------------------------------ aday önerisi (SENTETİK enjeksiyon)
def gauss(shape, x, y, flux, s=0.8):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return flux / (2 * math.pi * s * s) * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * s * s))


def run_detect(a, b, suspect=None, invalid=None):
    invalid = np.zeros(a.shape, bool) if invalid is None else invalid
    suspect = np.zeros(a.shape, bool) if suspect is None else suspect
    d = np.where(invalid, np.nan, b - a)
    v = d[np.isfinite(d)]
    sigma = 1.4826 * float(np.median(np.abs(v - np.median(v))))
    return detect_changes(a, b, d, invalid, suspect, sigma)


def test_candidate_detection_on_synthetic_injections():
    rng = np.random.default_rng(3)
    shape = (59, 59)
    base = lambda: rng.normal(0, 0.02, shape)
    static = [(12.3, 14.6, 40.0), (40.7, 20.2, 60.0), (30.1, 45.5, 50.0)]
    a = base() + sum(gauss(shape, x, y, f, 0.7) for x, y, f in static)
    # B: durağan yıldızlar farklı PSF genişliği ve alt-piksel kaymasıyla (toplam akı aynı) -> aday OLMAMALI
    b = base() + sum(gauss(shape, x + 0.2, y - 0.15, f, 1.0) for x, y, f in static)
    out = run_detect(a, b)
    assert out["candidates"] == [] and out["n_dropped_low_fraction"] >= 1
    # hareket: kaynak (20,30) -> (22.5,30)
    out = run_detect(a + gauss(shape, 20.0, 30.0, 30.0), b + gauss(shape, 22.5, 30.0, 30.0))
    mv = [c for c in out["candidates"] if c["classification"] == "possible_motion"]
    assert len(mv) == 1 and mv[0]["x"] == pytest.approx(22.5, abs=0.8) and mv[0]["x_from"] == pytest.approx(20.0, abs=0.8)
    assert mv[0]["shift_px"] == pytest.approx(2.5, abs=0.8)
    # parlaklık değişimi: (45,45)'teki kaynak 2 katına çıkar
    out = run_detect(a + gauss(shape, 45.0, 45.0, 30.0), b + gauss(shape, 45.0, 45.0, 60.0))
    br = [c for c in out["candidates"] if c["classification"] == "possible_brightness_change"]
    assert len(br) == 1 and br[0]["explanation"] == "brightened" and br[0]["frac_change"] == pytest.approx(0.5, abs=0.12)
    # şüpheli bayraklı piksele değen artık -> olası görüntü hatası
    sus = np.zeros(shape, bool)
    sus[10, 50] = True
    out = run_detect(a, b + gauss(shape, 50.0, 10.0, 30.0), suspect=sus)
    assert [c["classification"] for c in out["candidates"]] == ["possible_artifact"]
    # değişim yok + geçersiz bölge -> aday yok
    inv = np.zeros(shape, bool)
    inv[0:5, :] = True
    assert run_detect(a, a + rng.normal(0, 0.02, shape), invalid=inv)["candidates"] == []
