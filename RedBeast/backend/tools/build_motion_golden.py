"""Independent Astropy ICRS Cartesian position + velocity * elapsed Julian years.

This deliberately does not call apply_space_motion (which includes a different
light-time treatment), nor does it import the frontend's hand-written formula.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import astropy
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from blinkspace.targets import RESOURCES
from tools.build_motion_catalogue import ID_MAP
from tools.science_sources import sha256, write_json

YEARS = (2000.0, 2026.0, 2050.0, 2100.0)
BARNARD_2050 = [-0.017739342162699453, -1.8178101926870318, 0.15385109849645198]


def astropy_positions(star: dict) -> list[dict]:
    coord = SkyCoord(ra=star["ra"] * u.deg, dec=star["dec"] * u.deg,
                     distance=star["distancePc"] * u.pc,
                     pm_ra_cosdec=star["pmRa"] * u.mas / u.yr, pm_dec=star["pmDec"] * u.mas / u.yr,
                     radial_velocity=(star["radialVelocity"] if star["hasRadialVelocity"] else 0.0) * u.km / u.s,
                     obstime=Time(star["epoch"], format="jyear"), frame="icrs")
    origin = coord.cartesian.xyz.to_value(u.pc)
    velocity = coord.velocity.d_xyz.to_value(u.pc / u.yr)
    positions = []
    for year in YEARS:
        xyz = origin + velocity * (year - star["epoch"])
        positions.append({"year": year, "icrs_pc": xyz.tolist(), "three_pc": xyz[[0, 2, 1]].tolist()})
    return positions


def build_document(raw: dict, checksum: str) -> dict:
    stars = [{"id": ID_MAP.get(s["id"], s["id"]), "input": {k: v for k, v in s.items() if k != "color"},
              "positions": astropy_positions(s)} for s in raw["targets"]]
    actual = next(p["icrs_pc"] for s in stars if s["id"] == "barnard" for p in s["positions"] if p["year"] == 2050)
    if not np.allclose(actual, BARNARD_2050, rtol=0, atol=1e-12):
        raise RuntimeError(f"Mandatory Barnard 2050 reference differs: got {actual}; expected {BARNARD_2050}")
    return {"schema_version": 1, "model": "Astropy SkyCoord ICRS Cartesian position + velocity * delta Julian years; no apply_space_motion",
            "coordinate_system": {"icrs_pc": "ICRS Cartesian parsecs", "three_pc": "[ICRS x, ICRS z, ICRS y]"},
            "provenance": {"input_sha256": checksum, "astropy_version": astropy.__version__,
                           "source_url": "https://docs.astropy.org/en/stable/coordinates/velocities.html"}, "stars": stars}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=RESOURCES / "source_data/input_catalogue.json")
    ap.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "frontend/src/tests/golden/motion.json")
    args = ap.parse_args()
    content = args.input.read_bytes()
    doc = build_document(json.loads(content), sha256(content))
    write_json(args.output, doc)
    print(f"20 independent positions written to {args.output}; Barnard 2050 verified within 1e-12 pc")


if __name__ == "__main__":
    main()
