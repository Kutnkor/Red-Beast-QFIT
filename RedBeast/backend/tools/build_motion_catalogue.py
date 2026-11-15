"""Preserve the supplied astrometry; augment it with traceable temperature estimates.

Run: PYTHONPATH=backend python -m tools.build_motion_catalogue --input catalogue.json
Downloads are cached with exact requests and SHA-256, so rebuilding is offline after the first run.
The dwarf colour relation is a display estimate, not an individual temperature measurement.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from astropy import units as u

from blinkspace.targets import RESOURCES
from tools.science_sources import SOURCE_DIR, finite, sha256, source_bytes, tap_csv, utc_now, write_json

IRSA = "https://irsa.ipac.caltech.edu/TAP/sync"
MAMAJEK = "https://www.pas.rochester.edu/~emamajek/EEM_dwarf_UBVIJHK_colors_Teff.txt"
MOON = "https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html"
OBLIQUITY = "https://raw.githubusercontent.com/liberfa/erfa/master/src/obl06.c"
ID_MAP = {"barnard": "barnard", "epsilon": "eps-indi-b", "wise": "wise-0855", "rwaur": "rw-aur", "rdra": "r-dra"}
FIELD_MAP = {"parallax": "parallax_mas", "parallaxError": "parallax_err_mas", "pmRa": "pmra_masyr",
             "pmDec": "pmdec_masyr", "radialVelocity": "rv_kms", "hasRadialVelocity": "has_rv",
             "distancePc": "distance_pc", "magnitude": "g_mag", "colorIndex": "bp_rp",
             "spectralType": "spectral_type", "sourceUrl": "source_url"}


def mamajek_rows(data: bytes) -> tuple[list[dict], str]:
    text = data.decode("utf-8")
    version = re.search(r"^# Version\s+(\S+)", text, re.M)
    rows = []
    for line in text.splitlines():
        if re.match(r"^[OBAFGKMLTY]\d", line):
            values = line.split()
            if len(values) >= 12 and finite(values[1]):
                rows.append({"sptype": values[0], "teff": float(values[1]), "bprp": finite(values[11])})
    if not rows or not version:
        raise ValueError("Unrecognized Mamajek table; no temperatures inferred")
    return rows, version[1]


def estimate_temperature(star: dict, gaia: dict, table: list[dict], *, target: bool) -> dict:
    # The non-Gaia target colourIndex=3 in the old renderer was illustrative, not photometry.
    # Never treat it as a measured Gaia BP-RP; never use a dwarf calibration for a Mira/TTauri star.
    sid = str(star["id"])
    if target and sid == "barnard":
        sid = "4472832130942575872"
    measured = finite(gaia.get(sid))
    if measured is not None and measured > 0:
        return {"teff_k": measured, "teff_source": "gaia_gspphot"}
    if target and sid == "wise-0855":
        return {"teff_k": 250.0, "teff_source": "literature:2014ApJ...786L..18L",
                "teff_range_k": [225, 260], "teff_source_url": "https://doi.org/10.1088/2041-8205/786/2/L18",
                "teff_note": "Approximate temperature in Luhman (2014); model-dependent range 225–260 K."}
    if target and sid == "eps-indi-b":
        return {"teff_k": None, "teff_source": "none", "teff_note": "Unresolved pair; no single component temperature assigned to the system.",
                "components": [{"name": "Epsilon Indi Ba", "teff_k": 1320.0, "teff_range_k": [1300, 1340]},
                               {"name": "Epsilon Indi Bb", "teff_k": 910.0, "teff_range_k": [880, 940]}],
                "component_teff_source": "literature:2010A&A...510A..99K",
                "component_teff_source_url": "https://doi.org/10.1051/0004-6361/200912981",
                "component_teff_note": "Display midpoints of published BT-Settl atmospheric-fit ranges, not exact measurements."}
    if target and sid in ("rw-aur", "r-dra"):
        return {"teff_k": None, "teff_source": "none", "teff_note": "Dwarf calibration not applicable to this variable/evolved system; supplied colour is illustrative."}
    colour = finite(star.get("colorIndex"))
    points = sorted((r["bprp"], r["teff"]) for r in table if r["bprp"] is not None)
    if colour is not None and points[0][0] <= colour <= points[-1][0]:
        return {"teff_k": round(float(np.interp(colour, [p[0] for p in points], [p[1] for p in points])), 1),
                "teff_source": "mamajek_bprp", "teff_note": "Linear mean-dwarf BP-RP relation; approximate display temperature, no reddening correction."}
    spec = star.get("spectralType", "")
    match = next((r for r in table if r["sptype"] == spec), None)
    if match:
        return {"teff_k": match["teff"], "teff_source": "mamajek_sptype", "teff_note": "Mean dwarf spectral-type calibration."}
    return {"teff_k": None, "teff_source": "none"}


def convert_star(raw: dict, gaia: dict, table: list[dict], *, target: bool = False) -> dict:
    star = {k: v for k, v in raw.items() if k != "color"}
    if target:
        star["id"] = ID_MAP[raw["id"]]
        star.update(target_id=star["id"], catalogue_id=raw["id"])
    for old, new in FIELD_MAP.items():
        star[new] = raw.get(old)
    # Preserve original rv and hasRadialVelocity; expose missing RV as null canonically.
    if not star["has_rv"]:
        star["rv_kms"] = None
    if target and raw["id"] != "barnard":
        star["bp_rp"] = None
        star["color_index_note"] = "Original colorIndex is illustrative and retained only for input traceability; not Gaia photometry."
    if raw["id"] in ("barnard", "4472832130942575872"):
        star["sourceUrl"] = star["source_url"] = "https://simbad.cfa.harvard.edu/simbad/sim-id?Ident=NAME%20Barnard%27s%20star"
    star.update(estimate_temperature(star, gaia, table, target=target))
    return star


def build_reference(*, refresh=False) -> tuple[dict, list[dict]]:
    moon, moon_meta = source_bytes("nasa_moon_fact.html", MOON, refresh=refresh)
    plain = re.sub(r"<[^>]+>", " ", moon.decode())
    match = re.search(r"Apparent diameter\s*\(seconds of arc\)\s*(\d+)", plain)
    if not match:
        raise ValueError("NASA Moon Fact Sheet apparent diameter field changed")
    erfa, erfa_meta = source_bytes("erfa_obl06.c", OBLIQUITY, refresh=refresh)
    match_e = re.search(r"eps0\s*=\s*\(\s*([\d.]+)", erfa.decode())
    if not match_e:
        raise ValueError("ERFA IAU 2006 obliquity coefficient not found")
    units = "https://docs.astropy.org/en/stable/units/standard_units.html"
    return {
        "moon_mean_diameter_arcsec": {"value": float(match[1]), "source": MOON, "source_url": MOON,
                                       "note": "NASA mean values at opposition from Earth's equator; actual apparent diameter varies."},
        "obliquity_j2000_deg": {"value": float(match_e[1]) / 3600.0, "source": OBLIQUITY, "source_url": OBLIQUITY,
                               "bibcode": "2003A&A...412..567C", "note": "IAU 2006 J2000 mean obliquity, ERFA/SOFA obl06 constant term."},
        "pc_to_ly": {"value": u.pc.to(u.lyr), "source": units},
        "au_per_pc": {"value": u.pc.to(u.au), "source": units},
        "julian_year_seconds": {"value": u.yr.to(u.s), "source": units},
    }, [moon_meta, erfa_meta]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--gaia-tap-url", default=IRSA, help="Gaia DR3 TAP provider (IRSA default; ESA primary fallback supported)")
    ap.add_argument("--gaia-table", default="gaia_dr3_source", choices=["gaia_dr3_source", "gaiadr3.gaia_source"])
    args = ap.parse_args()
    content = args.input.read_bytes()
    raw = json.loads(content)
    schema_query = f"SELECT column_name, datatype FROM TAP_SCHEMA.columns WHERE table_name = '{args.gaia_table}' AND column_name IN ('source_id','teff_gspphot')"
    schema, schema_meta = tap_csv("gaia_teff_schema.csv", args.gaia_tap_url, schema_query, refresh=args.refresh)
    if not {"source_id", "teff_gspphot"} <= {r["column_name"].lower() for r in schema}:
        raise ValueError("Gaia Teff schema differs; stop rather than guess columns")
    ids = [str(s["id"]) for s in raw["stars"]]
    if not all(i.isdigit() for i in ids):
        raise ValueError("Gaia source identifiers must be decimal integers")
    query = f"SELECT source_id, teff_gspphot FROM {args.gaia_table} WHERE source_id IN (" + ",".join(ids) + ")"
    rows, teff_meta = tap_csv("gaia_teff.csv", args.gaia_tap_url, query, refresh=args.refresh)
    gaia = {str(r["source_id"]): finite(r["teff_gspphot"]) for r in rows}
    data, mamajek_meta = source_bytes("EEM_dwarf_UBVIJHK_colors_Teff.txt", MAMAJEK, refresh=args.refresh)
    table, version = mamajek_rows(data)
    reference, refs = build_reference(refresh=args.refresh)
    doc = {"schema_version": 1, "retrievedUtc": raw.get("retrievedUtc"), "catalogue": raw["catalogue"],
           "motionModel": raw.get("motionModel"), "reference": reference,
           "selection": {"rule": "parallax > 80 mas and parallax_over_error > 10", "n": len(raw["stars"]), "radius_pc": 12.5,
                         "note": "Input-selected sample of 120 objects, not a complete volume-limited census."},
           "stars": [convert_star(s, gaia, table) for s in raw["stars"]],
           "targets": [convert_star(s, gaia, table, target=True) for s in raw["targets"]],
           "provenance": {"input": "input_catalogue.json", "input_sha256": sha256(content), "retrieved_utc": utc_now(),
                          "source_url": "https://gea.esac.esa.int/archive/", "teff_query": query,
                          "temperature_sources": [schema_meta, teff_meta, dict(mamajek_meta, version=version, bibcode="2013ApJS..208....9P")],
                          "reference_sources": refs}}
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    (SOURCE_DIR / "input_catalogue.json").write_bytes(content)
    write_json(RESOURCES / "motion_catalogue.json", doc)
    print(json.dumps({"stars": len(doc["stars"]), "targets": len(doc["targets"]), "temperatures": {s: sum(x["teff_source"] == s for x in doc["stars"] + doc["targets"]) for s in sorted({x["teff_source"] for x in doc["stars"] + doc["targets"]})}}))


if __name__ == "__main__":
    main()
