"""
Per-point weighting: does holding the identity-bearing arcs actually buy them?

BACKLOG 40 found that weighting the emission COST moved almost nothing - two of
five shapes came out byte-identical - and that the candidate RADIUS is where
the freedom lives. `search.refine(weighted=True)` now changes three things at
once: per-point snap weights, per-point radii, and k from 10 to 18. A result
from that tells you nothing about which of the three did the work, and one of
them - more candidates - would help any route at all.

So four arms on ONE placement per shape, which makes the comparison exact:

    base      snap 1.0, radius 260 m, k 10          today's default
    wide      snap 1.0, radius 260 m, k 18          more candidates, nothing else
    radius    snap 1.0, per-point radius, k 18      the lever BACKLOG 40 found
    full      per-point snap AND radius, k 18       what refine(weighted=True) does

WHAT IS MEASURED, and why not shape_distance. POC 36 named a traced cactus at
distance 0.300 and failed a hand-drawn elephant at 0.066, and POC 35 found
`excursion` predicts naming where distance does not (p < 0.0001). Weighting is
also GUARANTEED to look worse on distance, because it buys the salient arcs by
spending error on the filler. So the primary readouts are:

    salient   mean route-to-template error over the most identity-bearing
              quarter of the contour - what weighting is supposed to buy
    filler    the same over the least identity-bearing quarter - what it spends
    excursion the measured predictor of naming, which must not get worse

If weighting works, `salient` falls from `wide` to `radius`/`full` and `filler`
rises. If `salient` does not fall, the idea is wrong however good the distance
looks. Either way this is a measurement, not a decision: shipping still waits
on a rater round, for the reason in saliency.py's docstring.

Run:  python -m experiments.poc38_weighting
Out:  results/poc38_weighting.json
"""

from __future__ import annotations

import json
import time

import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree

import routeshape.feasibility as rf
import routeshape.shapes.pack as pack
import routeshape.street_scale as ss
from routeshape.matching import NoRouteFoundError, _densify, run_poc2
from routeshape.metrics import excursion, shape_distance
from routeshape.paths import RESULTS
from routeshape.placement import (GRID_STEP_M, MIN_SEPARATION_M, build_center_grid,
                                  build_street_index, place_shape, select_candidates)
from routeshape.region.graph import region_graph
from routeshape.saliency import radii, weights as snap_weights
from routeshape.search import ROTATIONS_DEG, coarse_scan
from routeshape.shapes.library import resample_by_arclength

MODE, LAT, LON = "bike", 25.0400, 121.5400
HALF_M = 14000.0
OUT = RESULTS / "poc38_weighting.json"

# Hand-drawn only, on purpose. `saliency.discriminative` asks what stops a shape
# being one of the OTHERS in the library, so installing a subject twice - the
# cup and its traced twin - would tell it that nothing does.
SHAPES = ["cup", "gear", "house", "plane", "fish", "ghost"]

ARMS = ("base", "wide", "radius", "full")
QUARTILE = 0.25


def arm_settings(arm: str, shape: str, points: int):
    """(snap weight, candidate radius, k) for one arm."""
    if arm == "base":
        return 1.0, 260.0, 10
    if arm == "wide":
        return 1.0, 260.0, 18
    w = snap_weights(shape, points)
    if arm == "radius":
        return 1.0, radii(w), 18
    return w, radii(w), 18


def split_error(route_xy, target, weight):
    """Route-to-template error over the most and least salient quarters.

    Distance from each CONTOUR point to the route, not the other way round: the
    question is whether the route went where the shape needed it, and a route
    that skips an arc entirely has to be charged for it.
    """
    tree = cKDTree(_densify(np.vstack([route_xy, route_xy[:1]]), spacing=5.0))
    err, _ = tree.query(target)
    cut = max(1, int(round(QUARTILE * len(weight))))
    order = np.argsort(weight)
    return (float(err[order[-cut:]].mean()), float(err[order[:cut]].mean()),
            float(err.mean()))


def main() -> None:
    pack.install()
    scale = ss.scale_for(LAT, LON, MODE, rf.MODES[MODE]["street_scale_m"])
    t0 = time.time()
    graph = region_graph(LAT, LON, HALF_M, mode=MODE)
    tree = build_street_index(graph)
    to_xy = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_xy.transform(LON, LAT))
    print(f"{graph.number_of_nodes():,} nodes in {time.time() - t0:.0f}s\n")

    out = []
    for shape in SHAPES:
        floor = rf.min_distance_km(shape, MODE, scale)
        target_km = float(max(25.0, floor * 1.25))
        plan = rf.plan(shape, target_km, MODE, scale)
        if not plan.feasible:
            print(f"{shape}: skipped ({plan.reason})")
            continue
        width_m, points = float(plan.width_m), int(plan.points)
        dense = resample_by_arclength(shape, 4000)
        closed = np.vstack([dense, dense[:1]])
        centers, _, _ = build_center_grid(
            region, max(400.0, HALF_M - width_m * 0.75), GRID_STEP_M)
        scored = coarse_scan(tree, centers, shape, width_m, ROTATIONS_DEG)
        picks = select_candidates(scored, 1, MIN_SEPARATION_M)
        if not len(picks):
            print(f"{shape}: no placement")
            continue
        row = picks[0]
        centre, rotation = np.array([row["x"], row["y"]]), row["rotation"]
        # ONE placement for all four arms. Comparing arms across placements
        # would measure the placement, which is the larger effect by far.
        contour = place_shape(resample_by_arclength(shape, points), centre,
                              width_m, rotation)
        reference = place_shape(closed, centre, width_m, rotation)
        upright = place_shape(closed, centre, width_m, 0.0)
        w = snap_weights(shape, points)
        print(f"{shape}  {points} pts  {width_m:.0f} m wide  "
              f"rotation {rotation:.0f} deg")

        for arm in ARMS:
            snap, radius, k = arm_settings(arm, shape, points)
            t1 = time.time()
            try:
                fit = run_poc2(graph, contour, reference, k, snap,
                               radius_m=radius, deviation_weight=10.0)
            except NoRouteFoundError:
                print(f"  {arm:7s} no route")
                continue
            salient, filler, mean_err = split_error(fit["route_xy"], contour, w)
            record = {
                "shape": shape, "arm": arm, "points": points,
                "width_m": round(width_m, 1), "rotation": float(rotation),
                "route_km": round(fit["metrics"]["route_km"], 2),
                "distance": round(float(shape_distance(fit["route_xy"], upright)), 4),
                "excursion": round(float(excursion(fit["route_xy"], reference)), 4),
                "salient_m": round(salient, 1), "filler_m": round(filler, 1),
                "mean_m": round(mean_err, 1),
                "seconds": round(time.time() - t1, 1),
            }
            out.append(record)
            print(f"  {arm:7s} salient {salient:6.1f} m  filler {filler:6.1f} m"
                  f"  mean {mean_err:6.1f} m  exc {record['excursion']:.3f}"
                  f"  d {record['distance']:.3f}  {record['route_km']:5.1f} km",
                  flush=True)
            OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
        print()

    print(f"{len(out)} fits; wrote {OUT}")
    for arm in ARMS:
        group = [r for r in out if r["arm"] == arm]
        if not group:
            continue
        print(f"  {arm:7s} salient {np.mean([r['salient_m'] for r in group]):6.1f} m"
              f"  filler {np.mean([r['filler_m'] for r in group]):6.1f} m"
              f"  exc {np.mean([r['excursion'] for r in group]):.3f}"
              f"  d {np.mean([r['distance'] for r in group]):.3f}"
              f"  {np.mean([r['route_km'] for r in group]):5.1f} km")


if __name__ == "__main__":
    main()
