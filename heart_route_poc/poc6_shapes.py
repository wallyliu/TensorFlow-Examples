"""
POC 6 - is this a heart trick, or a shape pipeline?

POCs 1-5 built and repeatedly re-measured a generator for one shape. This runs
the whole thing unchanged on four shapes chosen to stress it differently, and
ranks the results with the metric POC 5's human data endorsed - ordered,
rotation-invariant Procrustes distance.

Rotation is searched again here, which reverses POC 3's upright default. Two
things changed: a rater called rotated and upright hearts equally heart-like, so
tilt is no longer a cost; and the metric is now rotation-invariant, so tilt
cannot be gamed either. That makes orientation a free parameter worth
exploiting - a star whose points fall along the avenues can only be found by
looking for it.

Run:  python poc6_shapes.py
Out:  poc6_shapes.png, poc6_results.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Transformer
from scipy.spatial import cKDTree

from heart_route_poc import download_walk_graph
from heart_route_poc2 import NoRouteFoundError, _densify, evaluate, run_poc2
from heart_route_poc3 import (
    GRID_STEP_M, MAX_GAP_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M, SEARCH_LAT,
    SEARCH_LON, build_center_grid, build_street_index, place_shape, select_candidates,
)
from shape_library import SHAPES, resample_by_arclength
from shape_metrics import shape_distance

WIDTH_M = 2000.0
N_POINTS = 40
CONTOUR_SAMPLES = 180
ROTATIONS_DEG = tuple(range(0, 360, 30))   # searched now: see module docstring
N_REFINE = 8
OUT_PNG = Path(__file__).with_name("poc6_shapes.png")
OUT_JSON = Path(__file__).with_name("poc6_results.json")


def coarse_scan(street_tree, centers, shape, width_m, rotations):
    """POC 3's stage-1 filter, for any shape. Same score, same rejection rule."""
    contour = resample_by_arclength(shape, CONTOUR_SAMPLES)
    rows = []
    for rotation in rotations:
        offsets = place_shape(contour, np.zeros(2), width_m, rotation)
        query = (centers[:, None, :] + offsets[None, :, :]).reshape(-1, 2)
        dists = street_tree.query(query)[0].reshape(len(centers), CONTOUR_SAMPLES)
        mean, p95 = dists.mean(axis=1), np.percentile(dists, 95, axis=1)
        score = np.where(dists.max(axis=1) > MAX_GAP_M, np.inf, mean + 0.5 * p95)
        for i, centre in enumerate(centers):
            rows.append((centre[0], centre[1], rotation, score[i], mean[i], p95[i], 0.0))
    return np.array(rows, dtype=[("x", float), ("y", float), ("rotation", float),
                                 ("score", float), ("mean", float), ("p95", float),
                                 ("worst", float)])


def refine(graph, shape, centre_xy, rotation, width_m=WIDTH_M, points=N_POINTS):
    """Fit a real route to one placement and score it with the endorsed metric."""
    target = place_shape(resample_by_arclength(shape, points), centre_xy, width_m, rotation)
    dense = resample_by_arclength(shape, 4000)
    reference = place_shape(np.vstack([dense, dense[:1]]), centre_xy, width_m, rotation)

    try:
        result = run_poc2(graph, target, reference, 10, 1.0,
                          radius_m=260.0, deviation_weight=10.0)
    except NoRouteFoundError:
        return None
    result.update(centre_xy=np.asarray(centre_xy), rotation=rotation,
                  reference=reference, shape=shape)
    # The template is the shape at THIS placement's scale but upright: the metric
    # normalises position, scale and orientation away, so only form is compared.
    result["distance"] = shape_distance(
        result["route_xy"], place_shape(np.vstack([dense, dense[:1]]), centre_xy, width_m, 0.0)
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shapes", default=",".join(SHAPES))
    parser.add_argument("--refine", type=int, default=N_REFINE)
    parser.add_argument("--width-m", type=float, default=WIDTH_M)
    args = parser.parse_args()

    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    crs = graph.graph["crs"]
    to_proj = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))

    tree = build_street_index(graph)
    centers, _, _ = build_center_grid(
        region, NETWORK_HALF_SIZE_M - args.width_m * 0.75, GRID_STEP_M
    )

    best_by_shape, summary = {}, []
    for shape in args.shapes.split(","):
        print(f"\n=== {shape} ===")
        t0 = time.perf_counter()
        scored = coarse_scan(tree, centers, shape, args.width_m, ROTATIONS_DEG)
        viable = int(np.isfinite(scored["score"]).sum())
        print(f"  coarse: {len(scored):,} placements, {viable:,} viable, "
              f"{time.perf_counter() - t0:.1f}s")

        shortlist = select_candidates(scored, args.refine, MIN_SEPARATION_M)
        results = []
        for rank, row in enumerate(shortlist, start=1):
            fitted = refine(graph, shape, np.array([row["x"], row["y"]]),
                            row["rotation"], args.width_m)
            if fitted is None:
                print(f"    #{rank}: infeasible")
                continue
            results.append(fitted)
            print(f"    #{rank}: distance {fitted['distance']:.3f}  "
                  f"{fitted['metrics']['route_km']:.2f} km  rot {fitted['rotation']:+.0f}°  "
                  f"backtracked {fitted['metrics']['backtracked_edges']}")

        if not results:
            print("  no feasible placement")
            continue
        best = min(results, key=lambda r: r["distance"])
        best_by_shape[shape] = best
        lat, lon = to_wgs.transform(best["centre_xy"][0], best["centre_xy"][1])[::-1]
        summary.append({
            "shape": shape, "distance": best["distance"],
            "route_km": best["metrics"]["route_km"],
            "detour_ratio": best["metrics"]["detour_ratio"],
            "backtracked": best["metrics"]["backtracked_edges"],
            "rotation": best["rotation"], "lat": float(lat), "lon": float(lon),
            "coarse_viable": viable, "coarse_total": len(scored),
        })

    OUT_JSON.write_text(json.dumps(summary, indent=1))

    print(f"\n{'shape':<11}{'distance':>10}{'route km':>10}{'detour':>9}"
          f"{'backtrk':>9}{'rot':>7}{'location':>22}")
    print("-" * 78)
    for row in sorted(summary, key=lambda r: r["distance"]):
        print(f"{row['shape']:<11}{row['distance']:>10.3f}{row['route_km']:>10.2f}"
              f"{row['detour_ratio']:>9.2f}{row['backtracked']:>9}{row['rotation']:>6.0f}°"
              f"{f'{row[chr(108)+chr(97)+chr(116)]:.4f}, {row[chr(108)+chr(111)+chr(110)]:.4f}':>22}")

    fig, axes = plt.subplots(1, len(best_by_shape), figsize=(6.2 * len(best_by_shape), 6.6))
    axes = np.atleast_1d(axes)
    for ax, (shape, best) in zip(axes, best_by_shape.items()):
        ox.plot_graph(graph, ax=ax, node_size=0, edge_color="#dddddd", edge_linewidth=0.35,
                      bgcolor="white", show=False, close=False)
        ref = best["reference"]
        ax.plot(ref[:, 0], ref[:, 1], color="#c94a3f", lw=1.6, ls="--", label="ideal", zorder=3)
        xy = best["route_xy"]
        ax.plot(xy[:, 0], xy[:, 1], color="#1f5f8b", lw=2.4, label="walking route", zorder=4)
        margin = 320.0
        ax.set_xlim(ref[:, 0].min() - margin, ref[:, 0].max() + margin)
        ax.set_ylim(ref[:, 1].min() - margin, ref[:, 1].max() + margin)
        m = best["metrics"]
        ax.set_title(f"{shape} — distance {best['distance']:.3f}\n"
                     f"{m['route_km']:.2f} km · detour {m['detour_ratio']:.2f}x · "
                     f"{m['backtracked_edges']} backtracked", fontsize=10)
        ax.legend(loc="upper right", fontsize=8)
    fig.suptitle("POC 6 — the same pipeline, four target shapes, Taipei walking streets",
                 fontsize=14)
    fig.savefig(OUT_PNG, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nsaved {OUT_PNG}")


if __name__ == "__main__":
    main()
