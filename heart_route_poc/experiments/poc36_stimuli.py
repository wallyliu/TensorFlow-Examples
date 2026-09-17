"""
Hand-drawn against traced, same subject, same option list, blind.

Five subjects exist twice now - elephant, crab, giraffe, maple, butterfly -
once as something I drew and once traced off the emoji. The rater sees one
route and picks a SUBJECT, so both versions have the same right answer and the
only thing being measured is which drawing gets the subject named.

Also in: six emoji that have no hand-drawn twin, three hand-drawn shapes that
three raters named 6/6 in POC 33 (they are the control on the other side - if
tracing wins everywhere including against these, that is a different claim from
winning against the ones I drew badly), and three of POC 29's originals as
anchors, as in POC 33.

One item per shape, the best of three placements, so the comparison is between
DRAWINGS and not between lucky placements. Routes are fitted with the
excursion limit in force (BACKLOG 34), which is itself untested in front of
raters and gets its first look here.

Run:  python -m experiments.poc36_stimuli
Out:  results/poc36_stimuli.json
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
OUT = RESULTS / "poc36_stimuli.json"

# (shape name, the label a rater picks, which arm of the comparison)
PAIRED = ["elephant", "crab", "giraffe", "maple", "butterfly"]
EMOJI_ONLY = ["mushroom", "turtle", "penguin", "whale", "bicycle", "cactus"]
HAND_KEPT = ["plane", "music_note", "christmas_tree"]
ANCHORS = {"heart": "愛心", "star5": "五角星", "trex": "恐龍"}


def plan_list() -> list:
    labels = dict(pack.LABELS) | ANCHORS
    rows = []
    for name in PAIRED:
        rows.append((name, labels[name], "hand"))
        rows.append(("e_" + name, emoji.LABELS[name], "traced"))
    for name in EMOJI_ONLY:
        rows.append(("e_" + name, emoji.LABELS[name], "traced"))
    for name in HAND_KEPT:
        rows.append((name, labels[name], "hand"))
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
        out.append({
            "shape": name, "label": label, "arm": arm, "city": CITY,
            "target_km": round(target, 1), "floor_km": round(floor, 1),
            "distance": round(float(best["distance"]), 4),
            "excursion": round(float(best["excursion"]), 4),
            "route_km": round(best["metrics"]["route_km"], 1),
            "xy": upright_points(best["route_xy"],
                                 place_shape(closed, best["centre"], width_m, 0.0)),
        })
        print(f"  {name:16s} {arm:7s} {target:5.1f} km -> "
              f"d={best['distance']:.3f} exc={best['excursion']:.3f} "
              f"{best['metrics']['route_km']:.1f} km ({time.time() - t1:.0f}s)",
              flush=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False))

    print(f"\n{len(out)} routes; wrote {OUT} ({OUT.stat().st_size / 1000:.0f} KB)")


if __name__ == "__main__":
    main()
