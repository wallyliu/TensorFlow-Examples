"""
The same blind task, with the ORIGINAL FIVE mixed in as anchors.

POC 32 found that below a shape distance of 0.10 - the closest this project
fits - the original five scored 27/28 and the new pack 16/32, Fisher p =
0.00005. If that is real it is the human-visible form of BACKLOG 23: the same
metric number means different things to different libraries, because the
metric is blind to the features that carry identity.

It is also confounded twice over. POC 29 offered five options and POC 32
sixteen, and more options make a task harder and "cannot tell" more
attractive; and the raters were different people. Neither confound survives
putting the old shapes and the new ones in ONE task, with one option list and
the same raters, which is what this builds.

Everything else follows POC 32: one network for the whole run, rotation swept
as the service sweeps it, every candidate placement kept so the hard stimuli
are real fitted routes rather than synthetic damage.

Run:  python -m experiments.poc33_anchored_stimuli
Out:  results/poc33_stimuli.json
"""

from __future__ import annotations

import json
import time

import numpy as np
from pyproj import Transformer

import routeshape.feasibility as rf
import routeshape.shapes.pack as pack
import routeshape.street_scale as ss
from experiments.poc32_pack_stimuli import upright_points
from routeshape.matching import NoRouteFoundError
from routeshape.paths import RESULTS
from routeshape.placement import (GRID_STEP_M, MIN_SEPARATION_M, build_center_grid,
                                  build_street_index, place_shape, select_candidates)
from routeshape.region.graph import region_graph
from routeshape.search import ROTATIONS_DEG, coarse_scan, refine
from routeshape.shapes.library import resample_by_arclength

MODE = "bike"
CITY, LAT, LON = "台北", 25.0400, 121.5400
HALF_M = 12000.0
CANDIDATES = 6
# The five POC 29 measured. They are the anchor: whatever this task's option
# count and this task's raters do to the numbers, it does it to these too.
ANCHORS = ["triangle", "heart", "star5", "crescent", "trex"]
OUT = RESULTS / "poc33_stimuli.json"


def target_for(floor_km: float) -> float:
    return float(min(40.0, max(20.0, floor_km * 1.5)))


def main() -> None:
    names = list(pack.install()) + ANCHORS
    scale = ss.scale_for(LAT, LON, MODE, rf.MODES[MODE]["street_scale_m"])
    print(f"{len(names)} shapes ({len(ANCHORS)} anchors); "
          f"street scale {scale:.0f} m")
    t0 = time.time()
    graph = region_graph(LAT, LON, HALF_M, mode=MODE)
    tree = build_street_index(graph)
    to_xy = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_xy.transform(LON, LAT))
    print(f"  {graph.number_of_nodes():,} nodes in {time.time() - t0:.0f}s")

    out = []
    for shape in names:
        floor = rf.min_distance_km(shape, MODE, scale)
        plan = rf.plan(shape, target_for(floor), MODE, scale)
        if not plan.feasible:
            print(f"  {shape}: {plan.reason}", flush=True)
            continue
        width_m, points = float(plan.width_m), int(plan.points)
        dense = resample_by_arclength(shape, 4000)
        closed = np.vstack([dense, dense[:1]])
        centers, _, _ = build_center_grid(
            region, max(400.0, HALF_M - width_m * 0.75), GRID_STEP_M)
        scored = coarse_scan(tree, centers, shape, width_m, ROTATIONS_DEG)
        if not np.isfinite(scored["score"]).any():
            print(f"  {shape}: no placement", flush=True)
            continue
        t1, kept = time.time(), []
        for row in select_candidates(scored, CANDIDATES, MIN_SEPARATION_M):
            centre = np.array([row["x"], row["y"]])
            try:
                fit = refine(graph, shape, centre, row["rotation"], width_m,
                             points=points)
            except NoRouteFoundError:
                fit = None
            if fit is None:
                continue
            kept.append({
                "shape": shape, "anchor": shape in ANCHORS, "city": CITY,
                "floor_km": round(floor, 1), "width_m": round(width_m),
                "points": points,
                "distance": round(float(fit["distance"]), 4),
                "route_km": round(fit["metrics"]["route_km"], 1),
                "xy": upright_points(fit["route_xy"],
                                     place_shape(closed, centre, width_m, 0.0)),
            })
        out.extend(kept)
        tag = " (anchor)" if shape in ANCHORS else ""
        print(f"  {shape:15s}{tag:9s} floor {floor:4.1f}, {len(kept)} routes, "
              f"{sorted(round(k['distance'], 3) for k in kept)} "
              f"({time.time() - t1:.0f}s)", flush=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False))

    d = np.array([o["distance"] for o in out])
    print(f"\n{len(out)} routes over {len(set(o['shape'] for o in out))} shapes, "
          f"distance {d.min():.3f}-{d.max():.3f}")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1000:.0f} KB)")


if __name__ == "__main__":
    main()
