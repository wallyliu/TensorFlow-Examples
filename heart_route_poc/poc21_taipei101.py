"""
Fit Taipei 101 to Taipei's bike network, and find out n_min rings.

101 was chosen over the Mona Lisa on POC 20's finding: this pipeline draws
shapes whose identity is in their outline, and a stepped tower is that case in
its purest form. Nobody recognises 101 by its shading.

It also turned up a fault in how n_min was computed, since fixed. The old rule
took "the smallest n from which loss stays below tolerance for ALL larger n",
chosen so a lucky alignment could not be mistaken for convergence. On 101 the
loss decays past the tolerance and then RINGS - isolated spikes back over the
line at 280 and 316 - because the sample count beats against the sixteen
repeated module steps. The rule read the last crossing and returned 320.

`route_feasibility.n_min` now takes a rolling median of the loss curve first,
which ignores a lucky dip and an unlucky beat alike. 101 comes out at 204
points, 72 km rather than 113. The five original shapes are unchanged, so this
corrects a real artefact rather than moving a threshold. Any shape with
repeated fine structure was affected: a gear, a comb, a skyline.

Upright only. A tilted building is not that building, the same constraint POC
12 measured for text.

Run:  python poc21_taipei101.py
Out:  poc21_taipei101.png, poc21_taipei101.json, gpx/taipei101.gpx
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

import route_feasibility as rf
import shape_library as sl
from heart_route_poc import download_walk_graph
from region_graph import RegionNotCovered, region_graph
from heart_route_poc2 import NoRouteFoundError
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M, SEARCH_LAT,
                              SEARCH_LON, build_center_grid, build_street_index,
                              place_shape, select_candidates)
from poc6_shapes import coarse_scan, refine
from poc15_big_network import HALF_SIZE_M
from poc15_wiggle import wander
from route_export import write_gpx
from shape_library import resample_by_arclength
from shape_metrics import alignment_angle
from taipei101 import outline

# Taken from the shape itself rather than pinned, so the run tracks whatever
# n_min currently says. The first fit was forced down to 176 because 204 needs
# a network wider than anything downloaded then - 2 of 16 placements were
# viable and the fit came out at 0.275. The regional cache now covers 北北基桃宜,
# so the honest number can be used.
POINTS = None            # resolved from n_min below
MODE = "bike"
ROTATIONS_DEG = (0.0,)     # a tilted building is not that building
N_CANDIDATES = 3
OUT_PNG = Path(__file__).with_name("poc21_taipei101.png")
OUT_JSON = Path(__file__).with_name("poc21_taipei101.json")


def main() -> None:
    cfg = rf.MODES[MODE]
    sl.register("taipei101", outline())
    points = POINTS or rf.n_min("taipei101")
    dense = resample_by_arclength("taipei101", 4000)
    perimeter = float(np.hypot(*np.diff(np.vstack([dense, dense[:1]]), axis=0).T).sum())
    width_m = points * cfg["street_scale_m"] / perimeter
    print(f"101 at {points} points: {width_m / 1000:.1f} km wide, "
          f"predicted {points * cfg['street_scale_m'] * cfg['detour'] / 1000:.0f} km",
          flush=True)

    # The network has to hold the shape AND leave somewhere to put it. At 176
    # points inside a network barely wider than the shape, 14 of 16 placements
    # were off the grid before scoring began, and the fit was whatever the two
    # survivors happened to give. Half a shape-width of slack on each side is
    # the cheapest thing that turns a forced placement into a chosen one.
    half_size = max(HALF_SIZE_M, width_m * 1.0)
    try:
        graph = region_graph(SEARCH_LAT, SEARCH_LON, half_size, mode=MODE)
    except RegionNotCovered as exc:
        print(f"  region cache insufficient ({exc}); downloading directly",
              flush=True)
        graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, half_size, mode=MODE)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    margin = max(300.0, half_size - width_m * 0.75)
    centers, _, _ = build_center_grid(region, margin, GRID_STEP_M)
    scored = coarse_scan(tree, centers, "taipei101", width_m, ROTATIONS_DEG)
    viable = int(np.isfinite(scored["score"]).sum())
    print(f"  {len(centers)} placements, {viable} viable", flush=True)
    if viable == 0:
        OUT_JSON.write_text(json.dumps({"status": "no placement",
                                        "width_m": width_m, "points": points}))
        print("  no placement fits")
        return

    best = None
    for row in select_candidates(scored, N_CANDIDATES, MIN_SEPARATION_M):
        centre = np.array([row["x"], row["y"]])
        try:
            fit = refine(graph, "taipei101", centre, row["rotation"], width_m,
                         points=points)
        except NoRouteFoundError:
            continue
        if fit is None:
            continue
        fit["wander"] = wander(
            fit["route_xy"],
            place_shape(np.vstack([dense, dense[:1]]), centre, width_m, 0.0))
        print(f"  candidate: distance {fit['distance']:.3f}, "
              f"wander {fit['wander']:.3f}, {fit['metrics']['route_km']:.1f} km",
              flush=True)
        if best is None or fit["distance"] < best["distance"]:
            best = fit
    if best is None:
        OUT_JSON.write_text(json.dumps({"status": "no route"}))
        print("  no route")
        return

    template = place_shape(np.vstack([dense, dense[:1]]),
                           best["centre_xy"], width_m, 0.0)
    upright = alignment_angle(best["route_xy"], template)
    gpx_dir = Path(__file__).with_name("gpx")
    gpx_dir.mkdir(exist_ok=True)
    write_gpx(best, graph.graph["crs"], gpx_dir / "taipei101.gpx",
              "台北101路線", "taipei101", MODE)

    result = {"status": "ok", "points": points, "width_m": width_m,
              "distance": best["distance"], "wander": best["wander"],
              "route_km": best["metrics"]["route_km"], "upright_deg": upright}
    OUT_JSON.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

    theta = np.radians(upright)
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 7))
    ideal = np.vstack([dense, dense[:1]])
    ax1.plot(ideal[:, 0], ideal[:, 1], lw=1.4, color="#9aa09c")
    ax1.set_title("the outline asked for", fontsize=10)
    xy = (best["route_xy"] - best["route_xy"].mean(axis=0)) @ rot.T
    ax2.plot(xy[:, 0], xy[:, 1], lw=1.3, color="#c0392b")
    ax2.set_title(f"the route, turned upright\n{best['metrics']['route_km']:.0f} km · "
                  f"shape distance {best['distance']:.3f}", fontsize=10)
    for ax in (ax1, ax2):
        ax.set_aspect("equal")
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)


if __name__ == "__main__":
    main()
