"""
POC 9 - does the feasibility calculator actually predict what the router does?

`route_feasibility` turns a distance into a width and a contour resolution using
two empirical constants: the street scale (160 m, POC 7) and a detour ratio of
1.30 that has never been tested outside 2 km-wide shapes. If the detour ratio
drifts with size or shape, every predicted distance drifts with it, and a UI
built on it would quietly lie.

Two things get measured:

  PREDICTION   plan() a shape to a target distance, fit the route, compare the
               actual length against the predicted one. That is the number a
               user would be shown.

  WINDOW       sweep n around the recommendation at one size per shape, to test
               WINDOW_FRACTION = 0.85 - which was fitted to two measurements of
               one shape and is the weakest thing in the module.

Run:  python poc9_validate.py
Out:  poc9_validation.png, poc9_validation.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

from heart_route_poc import download_walk_graph
from heart_route_poc3 import (
    GRID_STEP_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON,
    build_center_grid, build_street_index, select_candidates,
)
from poc6_shapes import ROTATIONS_DEG, coarse_scan, refine
from route_feasibility import (
    TAIPEI_STREET_SCALE_M, contour_points, n_min, perimeter, plan,
)
from shape_library import SHAPES

TARGETS_KM = [5.0, 10.0, 20.0]
N_SEARCH = 3
OUT_PNG = Path(__file__).with_name("poc9_validation.png")
OUT_JSON = Path(__file__).with_name("poc9_validation.json")


def fit_best(graph, tree, region, shape, width, points):
    """Search a few placements at this size and keep the best fit."""
    half = NETWORK_HALF_SIZE_M - width * 0.75
    if half <= GRID_STEP_M:
        return None
    centers, _, _ = build_center_grid(region, half, GRID_STEP_M)
    scored = coarse_scan(tree, centers, shape, width, ROTATIONS_DEG)
    shortlist = select_candidates(scored, N_SEARCH, MIN_SEPARATION_M)
    best = None
    for row in shortlist:
        fitted = refine(graph, shape, np.array([row["x"], row["y"]]),
                        row["rotation"], width, points=points)
        if fitted is not None and (best is None or fitted["distance"] < best["distance"]):
            best = fitted
    return best


def main() -> None:
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    print("=== prediction: does the promised distance match the route? ===")
    print(f"{'shape':<10}{'target':>8}{'width':>9}{'n':>5}{'predicted':>11}"
          f"{'actual':>9}{'error':>8}{'detour':>8}")
    print("-" * 70)
    rows = []
    for shape in SHAPES:
        for target in TARGETS_KM:
            p = plan(shape, target)
            if not p.feasible:
                continue
            fitted = fit_best(graph, tree, region, shape, p.width_m, p.points)
            if fitted is None:
                print(f"{shape:<10}{target:>7.0f}k   no placement fits the network")
                continue
            actual = fitted["metrics"]["route_km"]
            detour = fitted["metrics"]["detour_ratio"]
            err = (actual - p.predicted_km) / p.predicted_km * 100
            rows.append({"shape": shape, "target_km": target, "width_m": p.width_m,
                         "points": p.points, "predicted_km": p.predicted_km,
                         "actual_km": actual, "error_pct": err, "detour": detour,
                         "distance": fitted["distance"]})
            print(f"{shape:<10}{target:>7.0f}k{p.width_m / 1000:>8.1f}k{p.points:>5}"
                  f"{p.predicted_km:>10.1f}k{actual:>8.1f}k{err:>+7.0f}%{detour:>8.2f}",
                  flush=True)

    detours = np.array([r["detour"] for r in rows])
    errors = np.array([r["error_pct"] for r in rows])
    print(f"\ndetour ratio over {len(rows)} fits: mean {detours.mean():.3f}, "
          f"sd {detours.std():.3f}, range {detours.min():.2f}-{detours.max():.2f}")
    print(f"prediction error: mean {errors.mean():+.1f}%, "
          f"worst {errors[np.argmax(np.abs(errors))]:+.1f}%")

    print("\n=== window: is 0.85 of the cap the right place to sit? ===")
    print(f"{'shape':<10}{'cap':>6}{'n_min':>7}{'0.85 cap':>10}"
          f"{'best n':>8}{'best/cap':>10}")
    print("-" * 52)
    sweeps = []
    for shape in SHAPES:
        target = 20.0 if n_min(shape) > 40 else 10.0
        p = plan(shape, target)
        if not p.feasible:
            continue
        cap = max(1, int(perimeter(shape) * p.width_m / TAIPEI_STREET_SCALE_M))
        grid = sorted({max(n_min(shape), int(f * cap)) for f in (0.5, 0.7, 0.85, 1.0)})
        base = fit_best(graph, tree, region, shape, p.width_m, p.points)
        if base is None:
            continue
        curve = []
        for n in grid:
            fitted = refine(graph, shape, base["centre_xy"], base["rotation"],
                            p.width_m, points=n)
            if fitted is not None:
                curve.append({"n": n, "fraction": n / cap, "distance": fitted["distance"],
                              "backtracked": fitted["metrics"]["backtracked_edges"]})
        if not curve:
            continue
        best = min(curve, key=lambda c: c["distance"])
        sweeps.append({"shape": shape, "cap": cap, "n_min": n_min(shape),
                       "target_km": target, "curve": curve, "best": best})
        print(f"{shape:<10}{cap:>6}{n_min(shape):>7}{contour_points(shape, p.width_m):>10}"
              f"{best['n']:>8}{best['fraction']:>10.2f}", flush=True)

    OUT_JSON.write_text(json.dumps({"prediction": rows, "window": sweeps}, indent=1))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    colours = {"heart": "#c94a3f", "star5": "#2f6f9f", "crescent": "#1a7f37",
               "triangle": "#8a6d3b", "trex": "#6a3d9a"}
    for shape in SHAPES:
        pts = [(r["predicted_km"], r["actual_km"]) for r in rows if r["shape"] == shape]
        if pts:
            axes[0].scatter([p[0] for p in pts], [p[1] for p in pts], s=95,
                            color=colours[shape], label=shape, edgecolor="white", zorder=4)
    lim = max(max(r["actual_km"] for r in rows), max(r["predicted_km"] for r in rows)) * 1.08
    axes[0].plot([0, lim], [0, lim], color="#98a2ad", ls=":", lw=1.4, zorder=2)
    axes[0].set_xlim(0, lim); axes[0].set_ylim(0, lim)
    axes[0].set_xlabel("distance the calculator promises (km)")
    axes[0].set_ylabel("distance the route actually is (km)")
    axes[0].set_title("Promise versus delivery\ndotted line = perfect", fontsize=11)

    for entry in sweeps:
        xs = [c["fraction"] for c in entry["curve"]]
        ys = [c["distance"] for c in entry["curve"]]
        axes[1].plot(xs, ys, "-o", color=colours[entry["shape"]], lw=2,
                     markersize=7, label=entry["shape"])
    axes[1].axvline(0.85, color="#98a2ad", ls=":", lw=1.4)
    axes[1].annotate("the 0.85 the module assumes", (0.85, axes[1].get_ylim()[1]),
                     ha="right", va="top", fontsize=9, color="#68727d", rotation=90)
    axes[1].set_xlabel("n as a fraction of the window's cap")
    axes[1].set_ylabel("shape distance (lower is better)")
    axes[1].set_title("Where in the window the optimum sits", fontsize=11)

    for ax in axes:
        ax.grid(color="#dfe4e9", lw=0.7); ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.legend(fontsize=9, frameon=False)
    fig.suptitle("POC 9 — testing the two constants the feasibility calculator rests on",
                 fontsize=14)
    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nsaved {OUT_PNG}")


if __name__ == "__main__":
    main()
