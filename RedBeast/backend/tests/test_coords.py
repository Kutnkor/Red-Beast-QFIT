"""Koordinat biçimleri, sınırlar ve dönüşümler."""
import math

import pytest

from blinkspace.coords import (CoordinateError, angular_separation_deg, format_dec_dms, format_ra_hms, parse_dec,
                               parse_position, parse_ra)


@pytest.mark.parametrize("text,unit,expected", [
    ("269.452", "deg", 269.452),
    ("269,452", "deg", 269.452),              # Türkçe ondalık virgül
    (269.452, "auto", 269.452),
    ("17h57m48.498s", "auto", 269.452075),
    ("17:57:48.498", "auto", 269.452075),
    ("17 57 48.498", "auto", 269.452075),
    ("17 57 48.498", "hour", 269.452075),
    ("17.96347167", "hour", 269.452075),
    ("269d27m07.47s", "auto", 269.452075),
    ("08h55m10.831s", "auto", 133.7951292),   # yayımlanmış (WISE dönemi) WISE 0855 RA'sı
    ("0", "deg", 0.0),
    ("12h", "auto", 180.0),
    ("180deg", "auto", 180.0),
])
def test_ra_formats(text, unit, expected):
    value, _ = parse_ra(text, unit)
    assert value == pytest.approx(expected, abs=1e-5)


@pytest.mark.parametrize("text,expected", [
    ("4.693365", 4.693365),
    ("+04d41m36.11s", 4.6933639),
    ("-7d14m42.53s", -7.2451472),             # yayımlanmış (WISE dönemi) WISE 0855 Dec'i
    ("-07:14:42.53", -7.2451472),
    ("-07 14 42.53", -7.2451472),
    ("−07 14 42.53", -7.2451472),             # Unicode eksi
    ("-00 30 00", -0.5),                       # işaret sıfır derecede korunmalı
    ("90", 90.0),
    ("-90", -90.0),
    ("+66d45m", 66.75),
])
def test_dec_formats(text, expected):
    assert parse_dec(text) == pytest.approx(expected, abs=1e-6)


def test_ra_wrap_and_notes():
    v, notes = parse_ra("360", "deg")
    assert v == 0.0 and "ra_wrapped" in notes
    v, notes = parse_ra("-10", "deg")
    assert v == 350.0 and "ra_wrapped" in notes
    v, notes = parse_ra("370.5", "deg")
    assert v == pytest.approx(10.5) and "ra_wrapped" in notes
    v, notes = parse_ra("24:00:00", "hour")
    assert v == 0.0 and "ra_wrapped" in notes
    assert "ra_assumed_degrees" in parse_ra("12.5", "auto")[1]
    assert "ra_assumed_hours" in parse_ra("12 30 00", "auto")[1]
    assert parse_ra("12.5", "deg")[1] == ()


@pytest.mark.parametrize("text,unit,code", [
    ("", "auto", "empty"),
    ("abc", "auto", "not_a_number"),
    ("nan", "deg", "not_a_number"),
    ("inf", "deg", "not_a_number"),
    ("1e999", "deg", "not_finite"),
    ("25:00:00", "hour", "ra_out_of_range"),
    ("24.5", "hour", "ra_out_of_range"),
    ("-1", "hour", "ra_out_of_range"),
    ("1000", "deg", "ra_out_of_range"),
    ("12:61:00", "auto", "bad_sexagesimal"),
    ("12:30:60", "auto", "bad_sexagesimal"),
    ("12.5:30:00", "auto", "bad_sexagesimal"),
    ("-12:30:00", "auto", "ra_negative_sexagesimal"),
    ("12h30m", "deg", "unit_mismatch"),
    ("180d00m", "hour", "unit_mismatch"),
    ("x" * 50, "auto", "too_long"),
    ("12", "parsec", "bad_unit"),
])
def test_ra_rejects(text, unit, code):
    with pytest.raises(CoordinateError) as exc:
        parse_ra(text, unit)
    assert exc.value.code == code


@pytest.mark.parametrize("text,code", [
    ("90.0001", "dec_out_of_range"), ("-91", "dec_out_of_range"), ("95 00 00", "dec_out_of_range"),
    ("abc", "not_a_number"), ("", "empty"), ("12h30m", "unit_mismatch"), ("10 70 00", "bad_sexagesimal"),
    (float("nan"), "not_finite"), (True, "not_a_number"), (None, "not_a_number"),
])
def test_dec_rejects(text, code):
    with pytest.raises(CoordinateError) as exc:
        parse_dec(text)
    assert exc.value.code == code


def test_position_and_formatting_roundtrip():
    p = parse_position("17h57m48.498s", "+04d41m36.11s")
    assert p.ra_deg == pytest.approx(269.452075, abs=1e-5) and p.dec_deg == pytest.approx(4.6933639, abs=1e-6)
    assert format_ra_hms(p.ra_deg, 3) == "17h57m48.498s"
    assert format_dec_dms(p.dec_deg, 2) == "+04d41m36.11s"
    assert format_dec_dms(-0.5) == "-00d30m00.0s"
    assert format_ra_hms(359.9999999) == "00h00m00.00s"      # yuvarlama 24 saate taşmamalı
    q = parse_position(format_ra_hms(133.7951292, 4), format_dec_dms(-7.2451472, 3))
    assert q.ra_deg == pytest.approx(133.7951292, abs=1e-5) and q.dec_deg == pytest.approx(-7.2451472, abs=1e-6)


def test_angular_separation_known_values():
    assert angular_separation_deg(0, 0, 1, 0) == pytest.approx(1.0)
    assert angular_separation_deg(10, 90, 200, 90) == pytest.approx(0.0, abs=1e-9)
    assert angular_separation_deg(359.5, 0, 0.5, 0) == pytest.approx(1.0)            # RA sarması
    assert angular_separation_deg(0, 60, 1, 60) == pytest.approx(math.degrees(math.acos(
        math.sin(math.radians(60)) ** 2 + math.cos(math.radians(60)) ** 2 * math.cos(math.radians(1)))), rel=1e-9)


def test_eps_indi_b_is_not_the_primary_star():
    """Hedef kaydı ana yıldız değil, ~400″ uzaktaki B bileşenidir (SIMBAD değerleri kaynak dosyasından)."""
    from blinkspace.targets import load_targets
    t = load_targets()["eps-indi-b"]
    assert t["simbad_main_id"] == "* eps Ind B" and t["spectral_type"].startswith("T")
    p = t["primary_star"]
    sep = angular_separation_deg(t["ra_deg"], t["dec_deg"], p["ra_deg"], p["dec_deg"]) * 3600
    assert sep == pytest.approx(p["separation_arcsec"], abs=0.1) and 350 < sep < 450


def test_wise0855_reference_coordinate_is_old_epoch():
    """Yayımlanmış referans koordinat ~2010 dönemine aittir; J2026 arama merkezinden ~2′ uzaktadır."""
    from blinkspace.targets import load_targets
    t = load_targets()["wise-0855"]
    c = t["reference_coords"]
    p = parse_position(c["ra"], c["dec"])
    assert p.ra_deg == pytest.approx(c["ra_deg"], abs=1e-5)
    years = angular_separation_deg(p.ra_deg, p.dec_deg, t["ra_deg"], t["dec_deg"]) * 3600 / (t["pm_total_masyr"] / 1000)
    assert 9.5 < years < 11.5                      # J2000 konumundan ~10.4 yıl sonrası: WISE dönemi
    assert 100 < c["offset_from_search_center_arcsec"] < 150
