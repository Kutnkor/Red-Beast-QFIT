"""Build the real Hipparcos V<6.5 sky, with schema-checked VizieR input."""
from __future__ import annotations

import argparse
import csv
import io
import math
from urllib.parse import urlencode

import numpy as np
from astropy import units as u

from blinkspace.blackbody import temperature_to_rgb
from blinkspace.targets import RESOURCES
from tools.science_sources import finite, sha256, source_bytes, tap_csv, utc_now, write_json

VIZIER = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
TABLE = "I/239/hip_main"


def asu_rows(data: bytes):
    lines = [line for line in data.decode("utf-8").splitlines() if line.strip() and not line.startswith("#")]
    header = lines[0].split("\t")
    divider = next(i for i, line in enumerate(lines) if set(line.replace("\t", "").strip()) == {"-"})
    rows = list(csv.DictReader(io.StringIO("\n".join([lines[0], *lines[divider + 1:]])), delimiter="\t"))
    return [{k: (v or "").strip() for k, v in r.items()} for r in rows], set(header)


def query_asu(endpoint: str, refresh: bool):
    params = {"-source": TABLE, "-out": "HIP,RAICRS,DEICRS,Vmag,B-V,pmRA,pmDE", "Vmag": "<6.5", "-out.max": "1"}
    schema_data, schema_meta = source_bytes("hipparcos_asu_schema.tsv", endpoint + "?" + urlencode(params), refresh=refresh)
    _, columns = asu_rows(schema_data)
    required = {"HIP", "RAICRS", "DEICRS", "Vmag", "B-V", "pmRA", "pmDE"}
    if not required <= columns or not all(("#Column\t" + k + "\t") in schema_data.decode() or ("#Column " + k) in schema_data.decode() for k in required):
        raise ValueError(f"VizieR ASU schema differs: {columns}; inspect before using data")
    params["-out.max"] = "20000"
    params["-sort"] = "HIP"
    data, source = source_bytes("hipparcos_bright.tsv", endpoint + "?" + urlencode(params), refresh=refresh)
    rows, columns = asu_rows(data)
    return rows, schema_meta, source


def build_rows(rows: list[dict]) -> tuple[np.ndarray, list[int], dict]:
    packed, hips = [], []
    missing_colour = missing_pm = 0
    for row in rows:
        ra, dec, mag = (finite(row.get(k)) for k in ("RAICRS", "DEICRS", "Vmag"))
        if ra is None or dec is None or mag is None or mag >= 6.5:
            continue
        pmra, pmdec = finite(row.get("pmRA")), finite(row.get("pmDE"))
        if pmra is None or pmdec is None:
            missing_pm += 1
        # A unit-sphere tangent displacement avoids singularities at the pole.
        # No distance or RV is invented; only catalogue proper motion is applied.
        a, d = math.radians(ra), math.radians(dec)
        radial = np.array([math.cos(d) * math.cos(a), math.cos(d) * math.sin(a), math.sin(d)])
        east = np.array([-math.sin(a), math.cos(a), 0.0])
        north = np.array([-math.sin(d) * math.cos(a), -math.sin(d) * math.sin(a), math.cos(d)])
        tangent = ((pmra or 0.0) * east + (pmdec or 0.0) * north) * (2026.0 - 1991.25) * u.mas.to(u.rad)
        vector = radial + tangent
        vector /= np.linalg.norm(vector)
        bv = finite(row.get("B-V"))
        if bv is None or not (-0.4 <= bv <= 2.5):
            rgb = [1.0, 1.0, 1.0]
            missing_colour += 1
        else:
            teff = 4600.0 * (1 / (0.92 * bv + 1.7) + 1 / (0.92 * bv + 0.62))
            rgb = [v / 255 for v in temperature_to_rgb(teff)]
        packed.append([vector[0], vector[2], vector[1], mag, *rgb])
        hips.append(int(row["HIP"]))
    return np.asarray(packed, dtype="<f4"), hips, {"neutral_colour_count": missing_colour, "missing_proper_motion_count": missing_pm}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--tap-url", default=VIZIER, help="Official CDS TAP endpoint or its CDS mirror")
    ap.add_argument("--asu-url", help="Official CDS ASU mirror endpoint when Strasbourg TAP is unavailable")
    args = ap.parse_args()
    if args.asu_url:
        rows, schema_meta, source = query_asu(args.asu_url, args.refresh)
        query = None
    else:
        schema_query = "SELECT column_name, datatype, unit FROM TAP_SCHEMA.columns WHERE table_name = '\"I/239/hip_main\"'"
        schema, schema_meta = tap_csv("hipparcos_schema.csv", args.tap_url, schema_query, refresh=args.refresh)
        # VizieR exposes quoted column/table names in TAP_SCHEMA. Validate names before building ADQL.
        names = {r["column_name"].strip('"') for r in schema}
        if not names:
            schema_query = "SELECT column_name, datatype, unit FROM TAP_SCHEMA.columns WHERE table_name = 'I/239/hip_main'"
            schema, schema_meta = tap_csv("hipparcos_schema_unquoted.csv", args.tap_url, schema_query, refresh=args.refresh)
            names = {r["column_name"].strip('"') for r in schema}
        required = {"HIP", "RAICRS", "DEICRS", "Vmag", "B-V", "pmRA", "pmDE"}
        if not required <= names:
            raise RuntimeError(f"Hipparcos schema differs; missing {sorted(required - names)}; actual {sorted(names)}")
        query = 'SELECT HIP, RAICRS, DEICRS, Vmag, "B-V", pmRA, pmDE FROM "I/239/hip_main" WHERE Vmag < 6.5 ORDER BY HIP'
        rows, source = tap_csv("hipparcos_bright.csv", args.tap_url, query, refresh=args.refresh)
    data, hips, counts = build_rows(rows)
    if not 7000 <= len(hips) <= 11000:
        raise RuntimeError(f"Unexpected Hipparcos bright-star count {len(hips)}; stop for inspection")
    blob = data.tobytes()
    (RESOURCES / "bright_sky.bin").write_bytes(blob)
    doc = {"schema_version": 1, "catalogue": "ESA Hipparcos main catalogue (1997)", "partner_data": "ESA / CDS VizieR",
           "count": len(hips), "stride": 7, "components": ["x", "y", "z", "Vmag", "r", "g", "b"],
           "dtype": "float32", "byte_order": "little", "coordinate_system": "unit ICRS sphere mapped to Three [x,z,y]",
           "colour_space": "sRGB 0–1", "source_epoch_jyear": 1991.25, "epoch_jyear": 2026.0, "hip_ids": hips,
           "names": {}, "bytes": len(blob), "sha256": sha256(blob), **counts,
           "provenance": {"source_url": "https://cdsarc.cds.unistra.fr/viz-bin/cat/I/239", "schema": schema_meta,
                          "input": source, "adql": query, "retrieved_utc": utc_now(), "input_sha256": source["sha256"],
                          "query_protocol": "VizieR ASU TSV" if args.asu_url else "VizieR TAP ADQL",
                          "proper_motion": "unit-sphere tangent velocity * elapsed Julian years, then normalize; no radial motion or parallax",
                          "temperature": "Ballesteros (2012), EPL 97 34008; B-V formula valid display approximation; missing/out-of-domain colour neutral",
                          "temperature_source_url": "https://doi.org/10.1209/0295-5075/97/34008",
                          "colour": "Planck spectrum integrated against Wyman et al. 2013 analytic CIE 1931 approximations, normalized sRGB",
                          "colour_source_url": "https://jcgt.org/published/0002/02/01/"}}
    write_json(RESOURCES / "bright_sky.json", doc)
    print(f"{len(hips)} actual Hipparcos stars; {len(blob)} bytes; SHA-256 {doc['sha256']}")


if __name__ == "__main__":
    main()
