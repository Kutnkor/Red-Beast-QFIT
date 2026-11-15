"""Server mirror of the browser command schemas. These only produce proposals."""
from __future__ import annotations

import math


def text(*values):
    return {"type": "string", **({"enum": list(values)} if values else {})}


def number(low, high, integer=False):
    return {"type": "number", "minimum": low, "maximum": high, "integer": integer}


PROPERTIES = {
    "select_target": {"target_id": text()},
    "set_mode": {"mode": text("star", "neighbors", "observations")},
    "set_year": {"year": number(2000, 2100)},
    "set_frame": {"index": number(0, 10000, True)},
    "set_view_mode": {"view": text("single", "side", "diff", "stack", "trackstack")},
    "set_stage_view": {"view": text("frames", "timestack")},
    "toggle_layer": {"layer": text("environment", "trail", "grid", "sky", "gaia", "allwise", "predicted"), "on": {"type": "boolean"}},
    "open_drawer_tab": {"tab": text("frame", "layers", "marks", "curve", "wave", "task", "assistant")},
    "open_sources": {},
    "start_search": {"ra": text(), "dec": text(), "ra_unit": text("auto", "deg", "hour"), "fov_arcmin": number(2, 30)},
    "save_view": {},
    "open_target": {"target_id": text(), "page": text("star", "sky", "observations", "evolution")},
    "set_stellar_mode": {"mode": text("surface", "evolution", "education")},
    "set_sky_scale": {"scale": text("galaxy", "local")},
    "explain_value": {"field": text("distance", "parallax", "proper_motion", "radial_velocity", "teff", "position", "surface")},
    "show_observations": {"view": text("single", "side", "diff", "stack", "trackstack", "timestack", "blink"), "pair": text("current", "first_last")},
    "set_playback": {"playing": {"type": "boolean"}},
    "open_search": {},
}
CONFIRM = {"start_search", "save_view"}
# Commands that name a star: the id is checked against the loaded catalogue before a proposal is made.
TARGET_COMMANDS = {"select_target", "open_target"}


def schemas():
    return {name: {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
            for name, props in PROPERTIES.items()}


def validate_command(name, args):
    props = PROPERTIES.get(name)
    if props is None or not isinstance(args, dict) or set(args) != set(props):
        return False
    for key, value in args.items():
        rule = props[key]
        kind = rule["type"]
        if kind == "string" and (not isinstance(value, str) or not 1 <= len(value) <= 256):
            return False
        if kind == "boolean" and not isinstance(value, bool):
            return False
        if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))
                                 or not math.isfinite(value) or not rule["minimum"] <= value <= rule["maximum"]
                                 or (rule.get("integer") and value != int(value))):
            return False
        if "enum" in rule and value not in rule["enum"]:
            return False
    return True
