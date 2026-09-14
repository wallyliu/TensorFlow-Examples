"""
Does 101's stepped profile cost the detour, or does its size?

POC 21 drew 101 at n_min - 204 points, 12.3 km wide - and the silhouette came
out readable, but it took 110 km of road for a 57 km outline. That is a detour
of 1.93 where route_feasibility predicts 1.26, five times the +-15% the constant
is supposed to carry. Three explanations were available and only one survives.

Rivers and other barriers: rejected. Simplifying the route at 1120 m leaves
59.9 km against the template's 57.2 km, so the large-scale path is already the
right length and the excess 50 km is spread evenly across 50 m to 1 km. A
bridge detour would show up as a few long excursions, and there are none.

A street grid the upright shape cannot use: rejected. Taipei's grid is very
nearly axis-parallel already (bearings peak at 88-90 deg), and the median
distance to a street heading any chosen direction varies only from 161 m to
197 m over all twelve directions - 1.22x, nowhere near 1.93.

Which leaves the outline itself. 101's signature is sixteen module steps, and
every one of them is a 180 degree reversal. A road network cannot reverse in
place: the route leaves the street it came in on, rounds a block and comes
back, and that costs a detour no smooth curve pays. This POC tests exactly
that by fitting a notch-free 101 - same silhouette, same podium, same spire,
the stepped sides replaced by the straight taper they step around - at the
same size, in the same network, with the same one-anchor-per-street-scale
spacing, and comparing the detour.

If the steps are the cause, the smooth one lands near 1.26 and the stepped one
near 1.93. If both come out high, the cost is the size and the steps are
innocent.

They are innocent. The smooth 101 came out at detour 2.18 against the stepped
shape's 1.93 - not better, WORSE - so removing every reversal in the outline
made the road bill go up. Three hypotheses, three rejections, and what is left
is the one thing the three had in common: the size.

The likely mechanism is not that a big shape is intrinsically expensive but
that a big shape has nowhere to go. At 12.3 km only 27 of 1024 placements were
viable; at the 1-3 km sizes where DETOUR_RATIO = 1.25 was calibrated, thousands
are. 1.25 is therefore a best-of-thousands figure and 2.0 is close to a
take-what-you-get one, and the difference between them is selection, not
geometry. POC 9 half-saw this - it noted the size trend was "partly confounded"
by placement choice - and recorded the number anyway.

That makes the constant's +-15% uncertainty a claim about small shapes only.
Nothing here fixes it; the next measurement to take is detour against viable
placement count at fixed size, which separates the two for good.

Run:  python poc23_notches.py
Out:  poc23_notches.png, poc23_notches.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import route_feasibility as rf
import shape_library as sl
import taipei101 as t101
from heart_route_poc2 import NoRouteFoundError
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M, SEARCH_LAT,
                              SEARCH_LON, build_center_grid, build_street_index,
                              place_shape, select_candidates)
from poc6_shapes import coarse_scan, refine
from poc15_wiggle import wander
from region_graph import region_graph
from shape_library import resample_by_arclength

MODE = "bike"
ROTATIONS_DEG = (0.0,)
N_CANDIDATES = 2
OUT_PNG = Path(__file__).with_name("poc23_notches.png")
OUT_JSON = Path(__file__).with_name("poc23_notches.json")


def smooth_profile() -> list:
    """101 with the module steps replaced by the taper they step around.

    Only the stepped section changes. The podium, the base flare, the crown and
    the spire are the stepped shape's own, so any difference measured between
    the two is the steps and nothing else.
    """
    pts = [(t101.PODIUM_HALF, 0.0), (t101.PODIUM_HALF, t101.PODIUM_TOP),
           (t101.BASE_BOTTOM_HALF, t101.PODIUM_TOP),
           (t101.BASE_TOP_HALF, t101.BASE_TOP)]
    # The midline of the steps: each module runs from MODULE_BOTTOM_HALF to
    # MODULE_TOP_HALF, so the taper they straddle sits at their mean.
    mid = (t101.MODULE_BOTTOM_HALF + t101.MODULE_TOP_HALF) / 2
    pts.append((mid, t101.BASE_TOP))
    pts.append((mid, t101.MODULES_TOP))
    pts.append((t101.CROWN_HALF, t101.CROWN_TOP))
    pts.append((t101.SPIRE_HALF, t101.SPIRE_TOP))
    return pts


def mirror(half: list) -> np.ndarray:
    pts = [(x, y) for x, y in half]
    pts += [(-x, y) for x, y in reversed(half)]
    return np.array(pts, dtype=float)


def fit(name: str, width_m: float, graph, tree, region, cfg) -> dict:
    dense = resample_by_arclength(name, 4000)
    closed = np.vstack([dense, dense[:1]])
    perimeter = float(np.hypot(*np.diff(closed, axis=0).T).sum())
    # Size is held fixed and the point count follows from it, so both shapes
    # are drawn at the same physical scale AND the same anchor spacing - one
    # anchor per street_scale of outline. Fixing the point count instead, which
    # is the obvious thing to do, fixes neither: the smooth outline is shorter
    # in normalised units, so 204 points made it 15.0 km tall against the
    # stepped shape's 12.3 km, and at 15 km not one of 144 placements fitted in
    # the network. The comparison never happened.
    points = int(round(perimeter * width_m / cfg["street_scale_m"]))
    template_km = perimeter * width_m / 1000.0
    print(f"\n{name}: {points} points, {width_m / 1000:.1f} km wide, "
          f"outline {template_km:.1f} km", flush=True)

    margin = max(300.0, HALF - width_m * 0.75)
    centers, _, _ = build_center_grid(region, margin, GRID_STEP_M)
    scored = coarse_scan(tree, centers, name, width_m, ROTATIONS_DEG)
    viable = int(np.isfinite(scored["score"]).sum())
    print(f"  {len(centers)} placements, {viable} viable", flush=True)
    if viable == 0:
        return {"status": "no placement"}

    best = None
    for row in select_candidates(scored, N_CANDIDATES, MIN_SEPARATION_M):
        centre = np.array([row["x"], row["y"]])
        try:
            f = refine(graph, name, centre, row["rotation"], width_m,
                       points=points)
        except NoRouteFoundError:
            continue
        if f is None:
            continue
        f["wander"] = wander(f["route_xy"], place_shape(closed, centre, width_m, 0.0))
        f["detour"] = f["metrics"]["route_km"] / template_km
        print(f"  candidate: distance {f['distance']:.3f}, "
              f"detour {f['detour']:.2f}, {f['metrics']['route_km']:.1f} km",
              flush=True)
        if best is None or f["distance"] < best["distance"]:
            best = f
    if best is None:
        return {"status": "no route"}
    return {"status": "ok", "points": points, "width_m": width_m,
            "template_km": template_km, "distance": best["distance"],
            "wander": best["wander"], "detour": best["detour"],
            "route_km": best["metrics"]["route_km"],
            "route_xy": best["route_xy"]}


def main() -> None:
    global HALF
    cfg = rf.MODES[MODE]
    sl.register("taipei101", t101.outline())
    sl.register("taipei101_smooth", mirror(smooth_profile()))

    # The stepped shape at its own n_min sets the size; the smooth one is then
    # drawn at that same size, whatever point count that implies.
    points = rf.n_min("taipei101")
    dense = resample_by_arclength("taipei101", 4000)
    closed = np.vstack([dense, dense[:1]])
    per = float(np.hypot(*np.diff(closed, axis=0).T).sum())
    width_m = points * cfg["street_scale_m"] / per
    HALF = max(7000.0, width_m)

    graph = region_graph(SEARCH_LAT, SEARCH_LON, HALF, mode=MODE)
    from pyproj import Transformer
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    out = {}
    for name in ("taipei101", "taipei101_smooth"):
        out[name] = fit(name, width_m, graph, tree, region, cfg)

    fig, axes = plt.subplots(2, 2, figsize=(9, 9))
    for col, name in enumerate(("taipei101", "taipei101_smooth")):
        ideal = np.vstack([resample_by_arclength(name, 2000)] * 1)
        axes[0][col].plot(ideal[:, 0], ideal[:, 1], lw=1.2, color="#9aa09c")
        axes[0][col].set_title(name, fontsize=10)
        r = out[name]
        if r.get("status") == "ok":
            xy = r["route_xy"] - r["route_xy"].mean(axis=0)
            axes[1][col].plot(xy[:, 0], xy[:, 1], lw=1.1, color="#c0392b")
            axes[1][col].set_title(
                f"{r['route_km']:.0f} km · distance {r['distance']:.3f}\n"
                f"detour {r['detour']:.2f}", fontsize=10)
    for ax in axes.ravel():
        ax.set_aspect("equal"); ax.axis("off")
    fig.tight_layout(); fig.savefig(OUT_PNG, dpi=140)

    for r in out.values():
        r.pop("route_xy", None)
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print("\n" + json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
