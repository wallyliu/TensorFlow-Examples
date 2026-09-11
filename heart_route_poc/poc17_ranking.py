"""
Does the shortlist get ranked by a ruler that stopped working at 0.08?

Three raters settled that `shape_distance` stops tracking what people see above
roughly 0.08, and the search uses that same number to choose between placements
while two of the five shapes come out of it above that line. So the question was
whether the wander term POC 15 built would pick better routes.

ANSWER: no, and the reason is more useful than a yes would have been. Six
candidates per shape, every one fitted and scored both ways. Four of the five
shapes pick the same route either way; only the heart differs, and there the two
are tied on shape distance (0.077 against 0.079) while the v2 pick wanders much
less and comes out 0.9 km shorter. A small real gain, not a fix.

The finding is what fell out alongside it. Over all thirty candidates, the
coarse scan's rank and the final shape distance have a Spearman correlation of
-0.024 (p = 0.90). **The cheap pre-ranking carries no information about the
expensive result.** The best final route sat at coarse rank 4, 5, 2, 4 and 0 for
the five shapes.

Which means the star and the triangle were never a metric problem. Their best
placements were on the shortlist all along, at ranks 5 and 4, and the service
was only fitting the first three. Best-of-3 leaves two of five shapes above
0.10; best-of-6 leaves none.

This partly overturns POC 3. Its stage-1 score was meant to find good placements
cheaply. It finds ROUTABLE placements, which is worth having - it rejects the
ones with no network under them - but among those it is noise, and treating its
order as a quality ranking is what cost the star and the triangle.

Run:  python poc17_ranking.py
Out:  poc17_ranking.png, poc17_ranking.json
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
from heart_route_poc import download_walk_graph
from heart_route_poc2 import NoRouteFoundError
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M,
                              SEARCH_LAT, SEARCH_LON, build_center_grid,
                              build_street_index, place_shape, select_candidates)
from poc6_shapes import ROTATIONS_DEG, coarse_scan, refine
from poc15_wiggle import WANDER_WEIGHT, arclength, wander
from shape_library import SHAPES, resample_by_arclength
from shape_metrics import alignment_angle

MODE = "bike"
N_SHORTLIST = 6
TARGETS = {"heart": 10.0, "crescent": 9.0, "triangle": 8.0,
           "star5": 14.0, "trex": 34.0}
OUT_PNG = Path(__file__).with_name("poc17_ranking.png")
OUT_JSON = Path(__file__).with_name("poc17_ranking.json")


def main() -> None:
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M, mode=MODE)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    results = {}
    for shape in SHAPES:
        target_km = TARGETS[shape]
        plan = rf.plan(shape, target_km, MODE)
        if not plan.feasible:
            print(f"{shape}: {plan.reason}")
            continue
        width_m, points = plan.width_m, plan.points
        print(f"\n=== {shape} at {target_km} km: {width_m:.0f} m wide, {points} points")

        margin = max(400.0, NETWORK_HALF_SIZE_M - width_m * 0.75)
        centers, _, _ = build_center_grid(region, margin, GRID_STEP_M)
        scored = coarse_scan(tree, centers, shape, width_m, ROTATIONS_DEG)
        if not np.isfinite(scored["score"]).any():
            continue

        dense = resample_by_arclength(shape, 4000)
        candidates = []
        for rank, row in enumerate(select_candidates(scored, N_SHORTLIST,
                                                     MIN_SEPARATION_M)):
            centre = np.array([row["x"], row["y"]])
            try:
                fit = refine(graph, shape, centre, row["rotation"], width_m,
                             points=points)
            except NoRouteFoundError:
                continue
            if fit is None:
                continue
            template = place_shape(np.vstack([dense, dense[:1]]), centre, width_m, 0.0)
            w = wander(fit["route_xy"], template)
            candidates.append({
                "coarse_rank": rank,
                "shape_distance": fit["distance"],
                "wander": w,
                "v2": fit["distance"] + WANDER_WEIGHT * w,
                "route_km": fit["metrics"]["route_km"],
                "upright_deg": alignment_angle(fit["route_xy"], template),
            })

        if not candidates:
            continue
        by_old = min(candidates, key=lambda c: c["shape_distance"])
        by_new = min(candidates, key=lambda c: c["v2"])
        same = by_old["coarse_rank"] == by_new["coarse_rank"]
        results[shape] = {"width_m": width_m, "points": points,
                          "candidates": candidates,
                          "picked_by_shape_distance": by_old,
                          "picked_by_v2": by_new, "same_pick": same}

        print(f"  {'rank':>5}{'shape_d':>9}{'wander':>8}{'v2':>8}{'km':>7}")
        for c in candidates:
            mark = ""
            if c is by_old:
                mark += "  <- shape_distance"
            if c is by_new:
                mark += "  <- v2"
            print(f"  {c['coarse_rank']:>5}{c['shape_distance']:9.3f}"
                  f"{c['wander']:8.3f}{c['v2']:8.3f}{c['route_km']:7.1f}{mark}")
        if same:
            print("  same route either way")
        else:
            print(f"  DIFFERENT: shape_distance {by_old['shape_distance']:.3f} "
                  f"(wander {by_old['wander']:.3f}) vs "
                  f"v2 pick {by_new['shape_distance']:.3f} "
                  f"(wander {by_new['wander']:.3f})")

    fig, axes = plt.subplots(1, len(results), figsize=(3.4 * len(results), 3.8),
                             squeeze=False)
    for ax, (shape, r) in zip(axes[0], results.items()):
        xs = [c["shape_distance"] for c in r["candidates"]]
        ys = [c["wander"] for c in r["candidates"]]
        ax.scatter(xs, ys, s=42, color="#9aa09c", zorder=2)
        ax.scatter([r["picked_by_shape_distance"]["shape_distance"]],
                   [r["picked_by_shape_distance"]["wander"]],
                   s=110, facecolor="none", edgecolor="#b4622c", lw=2, zorder=3,
                   label="picked now")
        ax.scatter([r["picked_by_v2"]["shape_distance"]],
                   [r["picked_by_v2"]["wander"]],
                   s=110, facecolor="none", edgecolor="#2f5d50", lw=2, zorder=4,
                   label="picked by v2")
        ax.axvline(0.08, color="#c9c6bd", lw=1, ls="--", zorder=1)
        ax.set_title(shape, fontsize=10)
        ax.set_xlabel("shape distance", fontsize=9)
        ax.grid(alpha=0.25, lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0][0].set_ylabel("wander", fontsize=9)
    axes[0][0].legend(frameon=False, fontsize=8)
    fig.suptitle("Every shortlist candidate, scored both ways. "
                 "Dashed line is where the raters said shape distance stops working.",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
