"""
Round five: the sixteen traced shapes nobody has rated.

POC 39 settled what predicts whether a person names a route: which drawing it
is, and nothing else this project can compute. `shape_distance`, `excursion`
and the resolution floor all came in at the null. So the only instrument is a
person, and the product's hole is exactly the shapes no person has seen.

All sixteen emoji subjects are in that hole. Six have never been in front of a
rater at all - apple, rocket, anchor, guitar, sauropod, bicycle - and the other
ten carry two answers each from POC 36, which is not a rate. Three of those ten
are 0 of 2 (elephant, turtle, whale), and a round that leaves them there is a
round that cannot retire them either.

Three anchors from POC 33 ride along, as in every round since: heart, star5,
trex. They are 11/11 each, so a round where they slip is a round with something
wrong in it rather than a shape that failed.

One arm, one item per shape, best of three placements.

Run:  python -m experiments.poc41_stimuli
Out:  results/poc41_stimuli.json
"""

from __future__ import annotations

import json
import time

import numpy as np
from pyproj import Transformer

import routeshape.feasibility as rf
import routeshape.shapes.emoji as emoji
import routeshape.shapes.pack as pack
import routeshape.street_scale as ss
from experiments.poc32_pack_stimuli import upright_points
from routeshape.matching import NoRouteFoundError
from routeshape.metrics import excursion
from routeshape.paths import RESULTS
from routeshape.placement import (GRID_STEP_M, MIN_SEPARATION_M, build_center_grid,
                                  build_street_index, place_shape, select_candidates)
from routeshape.region.graph import region_graph
from routeshape.search import ROTATIONS_DEG, coarse_scan, refine
from routeshape.shapes.library import resample_by_arclength
from routeshape.wander import wander

MODE, CITY, LAT, LON = "bike", "台北", 25.0400, 121.5400
HALF_M = 14000.0
CANDIDATES = 3
WANDER_LIMIT, EXCURSION_LIMIT = 0.30, 0.08
OUT = RESULTS / "poc41_stimuli.json"

ANCHORS = {"heart": "愛心", "star5": "五角星", "trex": "恐龍"}


def plan_list() -> list:
    """Every traced subject with no hand-drawn twin, plus the three anchors.

    Read off the packs rather than typed out, so a subject retired between
    rounds cannot come back in through this file.
    """
    rows = []
    for name in emoji.PACK:
        if name in pack.PACK or name in pack.NAMED_BY_NOBODY:
            continue
        rows.append(("e_" + name, emoji.LABELS[name], "traced"))
    for name, label in ANCHORS.items():
        rows.append((name, label, "anchor"))
    return rows


def main() -> None:
    pack.install()
    emoji.install()
    scale = ss.scale_for(LAT, LON, MODE, rf.MODES[MODE]["street_scale_m"])
    jobs = plan_list()
    print(f"{len(jobs)} shapes; street scale {scale:.0f} m")
    t0 = time.time()
    graph = region_graph(LAT, LON, HALF_M, mode=MODE)
    tree = build_street_index(graph)
    to_xy = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_xy.transform(LON, LAT))
    print(f"  {graph.number_of_nodes():,} nodes in {time.time() - t0:.0f}s")

    out = []
    for name, label, arm in jobs:
        floor = rf.min_distance_km(name, MODE, scale)
        target = float(max(25.0, floor * 1.25))
        plan = rf.plan(name, target, MODE, scale)
        if not plan.feasible or plan.width_m > HALF_M:
            print(f"  {name}: skipped ({plan.reason})", flush=True)
            continue
        width_m, points = float(plan.width_m), int(plan.points)
        dense = resample_by_arclength(name, 4000)
        closed = np.vstack([dense, dense[:1]])
        centers, _, _ = build_center_grid(
            region, max(400.0, HALF_M - width_m * 0.75), GRID_STEP_M)
        scored = coarse_scan(tree, centers, name, width_m, ROTATIONS_DEG)
        if not np.isfinite(scored["score"]).any():
            print(f"  {name}: no placement", flush=True)
            continue
        t1, fits = time.time(), []
        for row in select_candidates(scored, CANDIDATES, MIN_SEPARATION_M):
            centre = np.array([row["x"], row["y"]])
            try:
                fit = refine(graph, name, centre, row["rotation"], width_m,
                             points=points)
            except NoRouteFoundError:
                fit = None
            if fit is None:
                continue
            fit["wander"] = wander(fit["route_xy"],
                                   place_shape(closed, centre, width_m, 0.0))
            fit["excursion"] = excursion(
                fit["route_xy"],
                place_shape(closed, centre, width_m, row["rotation"]))
            fit["centre"] = centre
            fit["rotation"] = row["rotation"]
            fits.append(fit)
        if not fits:
            print(f"  {name}: no route", flush=True)
            continue
        good = ([f for f in fits if f["wander"] <= WANDER_LIMIT
                 and f["excursion"] <= EXCURSION_LIMIT]
                or [f for f in fits if f["excursion"] <= EXCURSION_LIMIT] or fits)
        best = min(good, key=lambda f: f["distance"])
        # `subject` is what the two or three drawings of one thing have in
        # common; the task page groups on it to show one emoji arm per rater.
        out.append({
            "shape": name, "subject": name, "label": label, "arm": arm,
            "city": CITY,
            "target_km": round(target, 1), "floor_km": round(floor, 1),
            "distance": round(float(best["distance"]), 4),
            "excursion": round(float(best["excursion"]), 4),
            "route_km": round(best["metrics"]["route_km"], 1),
            "xy": upright_points(best["route_xy"],
                                 place_shape(closed, best["centre"], width_m, 0.0)),
        })
        print(f"  {name:18s} {arm:8s} {target:5.1f} km -> "
              f"d={best['distance']:.3f} exc={best['excursion']:.3f} "
              f"{best['metrics']['route_km']:.1f} km ({time.time() - t1:.0f}s)",
              flush=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False))

    print(f"\n{len(out)} routes; wrote {OUT} ({OUT.stat().st_size / 1000:.0f} KB)")


if __name__ == "__main__":
    main()
