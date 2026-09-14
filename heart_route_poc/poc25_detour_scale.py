"""
Calibrate the detour against the size of the shape.

POC 24 killed the explanation POC 23 offered. The claim was that 1.25 is a
best-of-thousands figure and 2.0 nearly take-what-you-get, so more placements
to choose from would close the gap. Measured, choice buys almost nothing:

    10 km target (2.5 km wide)   best-of-1 1.44 -> best-of-20 1.30
    50 km target (12.4 km wide)  best-of-1 2.11 -> best-of-7  2.21

The large curve sits about 0.8 above the small one at every k, so the two do
not overlay and size is the variable, not choice. That is worth saying plainly
because POC 23 published the opposite as its conclusion.

So the detour has to become a function of size, and this measures it. Two
shapes rather than one, because a constant fitted on a single outline is how
DETOUR_RATIO got into trouble in the first place, and four sizes spanning the
range the product offers.

The network size is bucketed to 2 km steps so that runs at nearby sizes share
a stitch. Stitching a 25 km box takes 75 seconds and there is no reason to do
it once per shape.

Run:  python poc25_detour_scale.py
Out:  poc25_detour_scale.png, poc25_detour_scale.json
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

import route_feasibility as rf
from heart_route_poc2 import NoRouteFoundError
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M, SEARCH_LAT,
                              SEARCH_LON, build_center_grid, build_street_index,
                              place_shape, select_candidates)
from poc6_shapes import coarse_scan, refine
from region_graph import region_graph
from shape_library import resample_by_arclength

SHAPES = ("heart", "star5")
TARGETS_KM = (10.0, 20.0, 35.0, 50.0)
FITS = 4
MODE = "bike"
PLACEMENT_SLACK = 1.0
BUCKET_M = 2000.0
OUT_PNG = Path(__file__).with_name("poc25_detour_scale.png")
OUT_JSON = Path(__file__).with_name("poc25_detour_scale.json")

_nets: dict = {}


def net_for(half_m: float):
    key = round(half_m)
    if key not in _nets:
        g = region_graph(SEARCH_LAT, SEARCH_LON, half_m, mode=MODE)
        to_proj = Transformer.from_crs("EPSG:4326", g.graph["crs"], always_xy=True)
        _nets.clear()          # one at a time: these are 70k-node graphs
        _nets[key] = {"graph": g, "tree": build_street_index(g),
                      "region": np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))}
    return _nets[key]


def measure(shape: str, target_km: float) -> dict:
    p = rf.plan(shape, target_km, MODE)
    if not p.feasible:
        return {"status": "infeasible", "reason": p.reason}
    width_m, points = float(p.width_m), int(p.points)
    dense = resample_by_arclength(shape, 4000)
    closed = np.vstack([dense, dense[:1]])
    perimeter = float(np.hypot(*np.diff(closed, axis=0).T).sum())
    template_km = perimeter * width_m / 1000.0
    half = math.ceil(max(4500.0, width_m * PLACEMENT_SLACK) / BUCKET_M) * BUCKET_M
    print(f"\n{shape} @ {target_km:.0f} km: {width_m / 1000:.1f} km wide, "
          f"{points} pts, outline {template_km:.1f} km, net +-{half:.0f} m",
          flush=True)

    net = net_for(half)
    margin = max(400.0, half - width_m * 0.75)
    centers, _, _ = build_center_grid(net["region"], margin, GRID_STEP_M)
    scored = coarse_scan(net["tree"], centers, shape, width_m, (0.0,))
    viable = int(np.isfinite(scored["score"]).sum())
    if viable == 0:
        return {"status": "no placement", "width_m": width_m}

    got = []
    for row in select_candidates(scored, FITS, MIN_SEPARATION_M):
        t0 = time.time()
        try:
            f = refine(net["graph"], shape, np.array([row["x"], row["y"]]),
                       row["rotation"], width_m, points=points)
        except NoRouteFoundError:
            f = None
        if f is None:
            continue
        km = f["metrics"]["route_km"]
        got.append({"distance": float(f["distance"]), "detour": km / template_km})
        print(f"    distance {f['distance']:.3f}  detour {got[-1]['detour']:.2f}  "
              f"{km:.1f} km ({time.time() - t0:.0f}s)", flush=True)
    if not got:
        return {"status": "no route", "width_m": width_m}
    # The pipeline keeps the lowest shape distance, so the detour a rider
    # actually gets is that fit's detour - not the best detour on offer.
    kept = min(got, key=lambda g: g["distance"])
    det = [g["detour"] for g in got]
    return {"status": "ok", "width_m": width_m, "points": points,
            "template_km": template_km, "viable": viable, "n_fits": len(got),
            "kept_detour": kept["detour"], "kept_distance": kept["distance"],
            "detour_mean": float(np.mean(det)), "detour_min": float(min(det)),
            "detour_max": float(max(det))}


def main() -> None:
    out = {}
    # Grouped by size so the bucketed network is built once per size, not once
    # per shape - a 25 km stitch costs 75 seconds.
    for target in TARGETS_KM:
        for shape in SHAPES:
            out[f"{shape}@{target:.0f}"] = measure(shape, target)
            OUT_JSON.write_text(json.dumps(out, indent=2))

    ok = {k: v for k, v in out.items() if v.get("status") == "ok"}
    w = np.array([v["width_m"] / 1000 for v in ok.values()])
    d = np.array([v["kept_detour"] for v in ok.values()])
    # Straight line in width. Deliberately the simplest form that fits: two
    # shapes and four sizes cannot support anything with more parameters, and
    # the constant being replaced had one.
    if len(w) >= 3:
        slope, intercept = np.polyfit(w, d, 1)
        resid = d - (slope * w + intercept)
        print(f"\ndetour = {intercept:.3f} + {slope:.4f} x width_km   "
              f"(residual sd {resid.std(ddof=1):.3f}, n={len(w)})")
        out["_fit"] = {"intercept": float(intercept), "slope_per_km": float(slope),
                       "residual_sd": float(resid.std(ddof=1)), "n": int(len(w))}
    OUT_JSON.write_text(json.dumps(out, indent=2))

    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for shape, color in zip(SHAPES, ("#2f5d50", "#b4622c")):
        xs = [v["width_m"] / 1000 for k, v in ok.items() if k.startswith(shape)]
        ys = [v["kept_detour"] for k, v in ok.items() if k.startswith(shape)]
        ax.plot(xs, ys, "o-", color=color, label=shape, lw=1.6, ms=6)
    ax.axhline(rf.DETOUR_RATIO, ls="--", lw=1, color="#888")
    ax.annotate(f"the constant, {rf.DETOUR_RATIO}", (0.4, rf.DETOUR_RATIO + 0.03),
                fontsize=8, color="#666")
    ax.set_xlabel("shape width (km)")
    ax.set_ylabel("route length ÷ outline length")
    ax.set_title("The detour is a function of size", fontsize=11)
    ax.legend(fontsize=9, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT_PNG, dpi=140)
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
