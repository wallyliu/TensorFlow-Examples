"""
POC 8 - how many contour points does a shape need, and how big must it be drawn?

POC 7 left a puzzle: sweeping the T-rex's contour resolution gave a NON-MONOTONIC
curve, best at 61 points and worse either side. More detail made the drawing
worse, which should not happen if more detail is simply better.

The explanation is that two opposing costs meet:

  SAMPLING LOSS falls as n rises. An n-point polygon is a lossy version of the
  shape, and how lossy is measurable in milliseconds without touching a map:
  shape_distance(n-point polygon, dense contour). A heart is under 0.02 by n=16;
  the T-rex is still at 0.024 by n=160, an order of magnitude more demanding.

  STREET-FITTING COST rises as n rises. Past the street grid's own scale (~160 m
  here, measured in POC 7) each extra contour point is another constraint the
  grid cannot satisfy, and the matcher pays for it in detours.

So n has a window: at least enough to represent the shape, at most one point per
street-scale of contour.

    n >= n_min(shape)                 sampling loss below tolerance
    n <= perimeter_metres / s         one point per street scale

and the window can be EMPTY, which is a statement about SIZE, not about n:

    W >= n_min * s / perimeter_normalised

The T-rex at 2 km needs n >= 92 to represent but allows at most 72 - empty,
so every n is a compromise, which is exactly the non-monotonic sweep POC 7 saw.
The prediction is that drawing it at 3 km opens the window and removes the
effect. That is what this tests.

Run:  python poc8_sizing.py
Out:  poc8_sizing.png, poc8_sizing.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
from pyproj import Transformer

from heart_route_poc import download_walk_graph
from heart_route_poc3 import (
    GRID_STEP_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON,
    build_center_grid, build_street_index, select_candidates,
)
from poc6_shapes import ROTATIONS_DEG, coarse_scan, refine
from shape_library import resample_by_arclength
from shape_metrics import shape_distance

SHAPE = "trex"
STREET_SCALE_M = 160.0
TOLERANCE = 0.05
WIDTHS = [2000.0, 3000.0, 4000.0]
SWEEP = [40, 61, 92, 120, 160]
N_SEARCH = 4
OUT_PNG = Path(__file__).with_name("poc8_sizing.png")
OUT_JSON = Path(__file__).with_name("poc8_sizing.json")


def perimeter(shape: str) -> float:
    pts = resample_by_arclength(shape, 4000)
    closed = np.vstack([pts, pts[:1]])
    return float(np.hypot(*np.diff(closed, axis=0).T).sum())


def sampling_loss(shape: str, n: int) -> float:
    """How much of the shape an n-point polygon throws away. No map involved."""
    return shape_distance(resample_by_arclength(shape, n), resample_by_arclength(shape, 4000))


def n_min(shape: str, tolerance: float = TOLERANCE, ceiling: int = 240) -> int:
    """Smallest n from which sampling loss stays below tolerance for all larger n."""
    grid = list(range(12, ceiling + 1, 4))
    losses = {n: sampling_loss(shape, n) for n in grid}
    for n in grid:
        if all(losses[m] < tolerance for m in grid if m >= n):
            return n
    return ceiling


def main() -> None:
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    p_norm = perimeter(SHAPE)
    lower = n_min(SHAPE)
    print(f"{SHAPE}: perimeter {p_norm:.2f}, n_min {lower} at tolerance {TOLERANCE}")
    print(f"minimum drawable width = {lower * STREET_SCALE_M / p_norm / 1000:.1f} km\n")

    results, fits = [], {}
    for width in WIDTHS:
        cap = int(p_norm * width / STREET_SCALE_M)
        window = f"{lower}-{cap}" if lower <= cap else "EMPTY"
        print(f"=== {width / 1000:.0f} km: n window {window} ===")

        centers, _, _ = build_center_grid(
            region, NETWORK_HALF_SIZE_M - width * 0.75, GRID_STEP_M)
        scored = coarse_scan(tree, centers, SHAPE, width, ROTATIONS_DEG)
        shortlist = select_candidates(scored, N_SEARCH, MIN_SEPARATION_M)

        search_n = min(max(lower, 40), cap)
        best = None
        for row in shortlist:
            fitted = refine(graph, SHAPE, np.array([row["x"], row["y"]]),
                            row["rotation"], width, points=search_n)
            if fitted is not None and (best is None or fitted["distance"] < best["distance"]):
                best = fitted
        if best is None:
            print("  no feasible placement")
            continue

        curve = []
        for n in SWEEP:
            fitted = refine(graph, SHAPE, best["centre_xy"], best["rotation"], width, points=n)
            if fitted is None:
                continue
            spacing = p_norm / n * width
            inside = lower <= n <= cap
            curve.append({"n": n, "spacing_m": spacing, "distance": fitted["distance"],
                          "backtracked": fitted["metrics"]["backtracked_edges"],
                          "route_km": fitted["metrics"]["route_km"], "in_window": inside})
            fits[(width, n)] = fitted
            print(f"  n={n:>4}  spacing {spacing:>4.0f} m  distance {fitted['distance']:.3f}"
                  f"  backtracked {fitted['metrics']['backtracked_edges']:>3}"
                  f"  route {fitted['metrics']['route_km']:>5.2f} km"
                  f"{'   <- in window' if inside else ''}", flush=True)

        distances = [c["distance"] for c in curve]
        best_n = SWEEP[int(np.argmin(distances))]
        rises = sum(1 for a, b in zip(distances, distances[1:]) if b > a)
        print(f"  best at n={best_n}; {rises} of {len(distances) - 1} steps get worse\n")
        results.append({"width_m": width, "cap": cap, "n_min": lower,
                        "window_empty": lower > cap, "curve": curve, "best_n": best_n})

    OUT_JSON.write_text(json.dumps(results, indent=1))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    colours = {2000.0: "#c94a3f", 3000.0: "#2f6f9f", 4000.0: "#1a7f37"}
    for entry in results:
        w = entry["width_m"]
        xs = [c["n"] for c in entry["curve"]]
        label = (f"{w / 1000:.0f} km — window "
                 + ("EMPTY" if entry["window_empty"] else f"{entry['n_min']}–{entry['cap']}"))
        axes[0].plot(xs, [c["distance"] for c in entry["curve"]], "-o", color=colours[w],
                     lw=2, markersize=7, label=label)
        axes[1].plot(xs, [c["backtracked"] for c in entry["curve"]], "-o", color=colours[w],
                     lw=2, markersize=7, label=label)
        for ax, key in ((axes[0], "distance"), (axes[1], "backtracked")):
            inside = [(c["n"], c[key]) for c in entry["curve"] if c["in_window"]]
            if inside:
                ax.scatter([p[0] for p in inside], [p[1] for p in inside], s=180,
                           facecolor="none", edgecolor=colours[w], linewidth=2, zorder=5)
    axes[0].set_ylabel("shape distance (lower is better)")
    axes[1].set_ylabel("backtracked segments")
    for ax in axes:
        ax.set_xlabel("contour points n")
        ax.grid(color="#dfe4e9", lw=0.7)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.legend(fontsize=9, frameon=False)
    axes[0].set_title("Rings mark n values inside the feasible window", fontsize=11)
    fig.suptitle("POC 8 — a shape too small for its own detail has no good n",
                 fontsize=14)
    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {OUT_PNG}")


if __name__ == "__main__":
    main()
