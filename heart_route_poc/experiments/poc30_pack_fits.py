"""
Do the new shapes actually draw on real streets?

shape_pack.py says what each outline needs in kilometres. That is the sampling
floor and nothing more - it says a route CAN represent the shape, not that a
street network will produce one anybody recognises. POC 29 measured how far
those two come apart, so a pack of shapes that has only been looked at on paper
is not evidence.

Each shape is fitted at a distance a person would actually ride, in Taipei, and
the result is drawn beside the outline it was asked for.

Run:  python poc30_pack_fits.py
Out:  poc30_pack_fits.png, poc30_pack_fits.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

import routeshape.recognition as rc
import routeshape.feasibility as rf
import routeshape.shapes.library as sl
import routeshape.shapes.pack as shape_pack
import routeshape.street_scale as ss
from routeshape.matching import NoRouteFoundError
from routeshape.placement import (GRID_STEP_M, MIN_SEPARATION_M, build_center_grid,
                              build_street_index, place_shape, select_candidates)
from routeshape.search import ROTATIONS_DEG, coarse_scan, refine
from routeshape.region.graph import region_graph
from routeshape.shapes.library import resample_by_arclength
from routeshape.metrics import alignment_angle

LAT, LON = 25.0400, 121.5400
MODE = "bike"
CANDIDATES = 4
SLACK = 1.0
OUT_PNG = Path(__file__).with_name("poc30_pack_fits.png")
OUT_JSON = Path(__file__).with_name("poc30_pack_fits.json")

_nets: dict = {}


def net_for(half):
    key = round(half / 2000) * 2000
    if key not in _nets:
        g = region_graph(LAT, LON, max(4500.0, key), mode=MODE)
        tp = Transformer.from_crs("EPSG:4326", g.graph["crs"], always_xy=True)
        _nets.clear()
        _nets[key] = {"graph": g, "tree": build_street_index(g),
                      "region": np.array(tp.transform(LON, LAT))}
    return _nets[key]


def fit_one(name, target_km, scale):
    p = rf.plan(name, target_km, MODE, scale)
    if not p.feasible:
        return {"status": "infeasible", "reason": p.reason}
    width_m, points = float(p.width_m), int(p.points)
    dense = resample_by_arclength(name, 4000)
    closed = np.vstack([dense, dense[:1]])
    half = max(4500.0, width_m * SLACK)
    net = net_for(half)
    centers, _, _ = build_center_grid(net["region"],
                                      max(400.0, half - width_m * 0.75), GRID_STEP_M)
    scored = coarse_scan(net["tree"], centers, name, width_m, ROTATIONS_DEG)
    if not np.isfinite(scored["score"]).any():
        return {"status": "no placement"}
    best = None
    for row in select_candidates(scored, CANDIDATES, MIN_SEPARATION_M):
        try:
            f = refine(net["graph"], name, np.array([row["x"], row["y"]]),
                       row["rotation"], width_m, points=points)
        except NoRouteFoundError:
            f = None
        if f is None:
            continue
        if best is None or f["distance"] < best["distance"]:
            best = f
    if best is None:
        return {"status": "no route"}
    template = place_shape(closed, best["centre_xy"], width_m, 0.0)
    ang = np.radians(alignment_angle(best["route_xy"], template))
    rot = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    xy = (best["route_xy"] - best["route_xy"].mean(axis=0)) @ rot.T
    return {"status": "ok", "distance": float(best["distance"]),
            "route_km": best["metrics"]["route_km"], "points": points,
            "width_m": width_m,
            "recognition": rc.recognition_rate(name, float(best["distance"])),
            "xy": xy}


def main() -> None:
    shape_pack.install()
    scale = ss.scale_for(LAT, LON, MODE, rf.MODES[MODE]["street_scale_m"])
    names = list(shape_pack.PACK)
    # Ride each at 1.6x its own floor, so none is judged at a size it was never
    # going to manage, and none is given so much room that the test is trivial.
    out, drawn = {}, []
    for name in names:
        floor = rf.min_distance_km(name, MODE, scale)
        target = round(max(10.0, floor * 1.6))
        t0 = time.time()
        r = fit_one(name, target, scale)
        out[name] = {k: v for k, v in r.items() if k != "xy"}
        out[name]["target_km"] = target
        if r.get("status") == "ok":
            drawn.append((name, target, r))
            print(f"  {name:11s} {target:>3.0f} km -> {r['route_km']:>5.1f} km, "
                  f"distance {r['distance']:.3f}, "
                  f"recognised ~{r['recognition']:.0%} ({time.time() - t0:.0f}s)",
                  flush=True)
        else:
            print(f"  {name:11s} {target:>3.0f} km -> {r.get('status')}", flush=True)
        OUT_JSON.write_text(json.dumps(out, indent=2))

    n = len(drawn)
    fig, axes = plt.subplots(2, n, figsize=(1.7 * n, 4.2))
    if n == 1:
        axes = axes.reshape(2, 1)
    for col, (name, target, r) in enumerate(drawn):
        ideal = resample_by_arclength(name, 600)
        ideal = np.vstack([ideal, ideal[:1]])
        axes[0][col].plot(ideal[:, 0], ideal[:, 1], lw=1.2, color="#9aa09c")
        axes[0][col].set_title(name, fontsize=9)   # ASCII: the plot font has no CJK
        axes[1][col].plot(r["xy"][:, 0], r["xy"][:, 1], lw=1.0, color="#c0392b")
        axes[1][col].set_title(f"{r['route_km']:.0f} km · {r['distance']:.3f}",
                               fontsize=8)
    for ax in axes.ravel():
        ax.set_aspect("equal"); ax.axis("off")
    fig.tight_layout(); fig.savefig(OUT_PNG, dpi=130)
    print(f"\nwrote {OUT_PNG.name}")


if __name__ == "__main__":
    main()
