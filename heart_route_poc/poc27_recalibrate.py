"""
Re-measure the early-warning threshold with the rotations the SERVICE uses.

POC 27 scanned one rotation. The service sweeps twelve, and coarse_scan returns
a row per centre AND rotation, so the rate computed from it meant something
different - and something that could exceed 1. Keelung, the case the whole
check exists for, went straight through.

The rate that carries the meaning is CENTRES WITH AT LEAST ONE WORKABLE
ROTATION over centres tried: how many places in this city the shape fits. That
reduces to POC 27's number when there is one rotation, so the two are the same
measurement, but the threshold has to be re-read off the twelve-rotation sweep
because a shape that fits at some angle fits more often than one pinned upright.

Only the scans re-run. The shape distances are POC 27's, already measured; no
route is fitted again.

Run:  python poc27_recalibrate.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

import route_feasibility as rf
import shape_library as sl
import street_scale as ss
from heart_route_poc3 import GRID_STEP_M, build_center_grid, build_street_index
from poc6_shapes import ROTATIONS_DEG, coarse_scan
from region_graph import RegionNotCovered, region_graph
from poc27_early_warning import CASES, MODE, PLACEMENT_SLACK

SRC = Path(__file__).with_name("poc27_early_warning.json")
OUT = Path(__file__).with_name("poc27_recalibrate.json")

_nets: dict = {}


def net_for(lat, lon, half):
    key = (round(lat, 4), round(lon, 4), round(half))
    if key not in _nets:
        g = region_graph(lat, lon, half, mode=MODE)
        tp = Transformer.from_crs("EPSG:4326", g.graph["crs"], always_xy=True)
        _nets.clear()
        _nets[key] = {"graph": g, "tree": build_street_index(g),
                      "region": np.array(tp.transform(lon, lat))}
    return _nets[key]


def main() -> None:
    known = json.loads(SRC.read_text())
    out = {}
    for shape, km, city, lat, lon in CASES:
        key = f"{shape}@{km:.0f}/{city}"
        prev = known.get(key, {})
        if prev.get("status") != "ok":
            continue
        scale = ss.scale_for(lat, lon, MODE, rf.MODES[MODE]["street_scale_m"])
        p = rf.plan(shape, km, MODE, scale)
        width_m = float(p.width_m)
        half = max(4500.0, width_m * PLACEMENT_SLACK)
        try:
            net = net_for(lat, lon, half)
        except RegionNotCovered:
            continue
        centers, _, _ = build_center_grid(
            net["region"], max(400.0, half - width_m * 0.75), GRID_STEP_M)
        scored = coarse_scan(net["tree"], centers, shape, width_m, ROTATIONS_DEG)
        placeable = int(np.isfinite(scored["score"])
                        .reshape(len(ROTATIONS_DEG), len(centers)).any(axis=0).sum())
        rate = placeable / max(1, len(centers))
        out[key] = {"rate": rate, "placeable": placeable, "centers": len(centers),
                    "distance": prev["kept_distance"],
                    "one_rotation_rate": prev["viable_rate"]}
        print(f"  {key:22s} 1-rot {prev['viable_rate']:>6.1%} -> "
              f"12-rot {rate:>6.1%}   distance {prev['kept_distance']:.3f}",
              flush=True)
        OUT.write_text(json.dumps(out, indent=2))

    poor = sorted(v["rate"] for v in out.values() if v["distance"] >= 0.18)
    rest = sorted(v["rate"] for v in out.values() if v["distance"] < 0.18)
    print(f"\npoor (>=0.18): {[f'{r:.1%}' for r in poor]}")
    print(f"rest:          {[f'{r:.1%}' for r in rest]}")
    if poor and rest:
        print(f"\nhighest poor {max(poor):.1%}, lowest other {min(rest):.1%}, "
              f"gap {min(rest) - max(poor):+.1%}")
        if min(rest) > max(poor):
            print(f"separable; midpoint threshold = {(min(rest) + max(poor)) / 2:.2f}")
        else:
            print("NOT separable at twelve rotations - the check cannot be used as is")
    OUT.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
