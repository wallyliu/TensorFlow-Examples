"""
POC 10 - re-baselining on a network a bicycle can actually use.

POCs 1-9 were built on the walking network the original brief specified. Asked
to produce cycling routes instead, the walking results measured 31% of their
length unrideable and 12 to 27 dismounts per loop, so the question is not
"filter differently" but "which of nine POCs' numbers survive".

What survives is everything that never touched a map: the shape metric, the
perceptual threshold of ~0.10, the tilt and feature findings from three raters,
the matcher, and n_min - which is a property of a shape, not a city. What has to
be re-measured is every constant derived from the network: its characteristic
scale, the detour ratio, and whether concave shapes remain routable at all once
one-way restrictions apply.

That last one is the real risk. POC 6 measured the star needing 20 backtracked
segments and the crescent 14. A pedestrian may walk back up a one-way street; a
cyclist may not, so shapes that depend on backtracking can become unroutable
rather than merely worse.

Run:  python poc10_bike.py
Out:  poc10_bike.png, poc10_bike.json
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
from scipy.spatial import cKDTree

from heart_route_poc import download_walk_graph
from heart_route_poc2 import NoRouteFoundError
from heart_route_poc3 import (
    GRID_STEP_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON,
    build_center_grid, build_street_index, select_candidates,
)
from poc6_shapes import ROTATIONS_DEG, WIDTH_M, coarse_scan, refine
from shape_library import SHAPES, resample_by_arclength

MODES = ["walk", "bike"]
SPACING_SWEEP = [40, 55, 70, 90, 120]      # contour points, for the scale sweep
SCALE_SHAPE = "heart"
N_SEARCH = 4
OUT_PNG = Path(__file__).with_name("poc10_bike.png")
OUT_JSON = Path(__file__).with_name("poc10_bike.json")


def perimeter(shape: str) -> float:
    pts = resample_by_arclength(shape, 4000)
    closed = np.vstack([pts, pts[:1]])
    return float(np.hypot(*np.diff(closed, axis=0).T).sum())


def network_stats(graph, tree, region, rng) -> dict:
    """Density, as a random point's distance to the nearest piece of network."""
    samples = region + rng.uniform(-2500, 2500, size=(20000, 2))
    d = tree.query(samples)[0]
    length = sum(data["length"] for _, _, data in graph.edges(data=True))
    return {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
            "km_of_network": length / 1000.0,
            "median_to_network_m": float(np.median(d)),
            "p90_to_network_m": float(np.percentile(d, 90))}


def main() -> None:
    rng = np.random.default_rng(0)
    results = {}

    for mode in MODES:
        print(f"\n================ {mode} ================")
        graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M, mode=mode)
        to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
        region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
        tree = build_street_index(graph)
        stats = network_stats(graph, tree, region, rng)
        print(f"  {stats['nodes']:,} nodes, {stats['km_of_network']:,.0f} km of network, "
              f"random point {stats['median_to_network_m']:.0f} m from it (median)")

        centers, _, _ = build_center_grid(
            region, NETWORK_HALF_SIZE_M - WIDTH_M * 0.75, GRID_STEP_M)

        fits = {}
        print(f"\n  {'shape':<10}{'distance':>10}{'route km':>10}{'detour':>9}"
              f"{'backtrk':>9}{'status':>12}")
        print("  " + "-" * 60)
        for shape in SHAPES:
            scored = coarse_scan(tree, centers, shape, WIDTH_M, ROTATIONS_DEG)
            viable = int(np.isfinite(scored["score"]).sum())
            if viable == 0:
                print(f"  {shape:<10}{'':>38}{'no placement':>12}")
                fits[shape] = {"status": "no placement"}
                continue
            shortlist = select_candidates(scored, N_SEARCH, MIN_SEPARATION_M)
            best, failures = None, 0
            for row in shortlist:
                try:
                    fitted = refine(graph, shape, np.array([row["x"], row["y"]]),
                                    row["rotation"], WIDTH_M)
                except NoRouteFoundError:
                    failures += 1
                    continue
                if fitted is None:
                    failures += 1
                    continue
                if best is None or fitted["distance"] < best["distance"]:
                    best = fitted
            if best is None:
                print(f"  {shape:<10}{'':>38}{'unroutable':>12}")
                fits[shape] = {"status": "unroutable", "failures": failures}
                continue
            m = best["metrics"]
            fits[shape] = {"status": "ok", "distance": best["distance"],
                           "route_km": m["route_km"], "detour": m["detour_ratio"],
                           "backtracked": m["backtracked_edges"],
                           "failed_placements": failures}
            print(f"  {shape:<10}{best['distance']:>10.3f}{m['route_km']:>10.2f}"
                  f"{m['detour_ratio']:>9.2f}{m['backtracked_edges']:>9}"
                  f"{f'{failures}/{len(shortlist)} failed' if failures else 'ok':>12}")

        # The network's characteristic scale: the contour spacing at which
        # sampling stops helping, measured the way POC 7 measured it for walking.
        print(f"\n  contour-spacing sweep on the {SCALE_SHAPE}:")
        scored = coarse_scan(tree, centers, SCALE_SHAPE, WIDTH_M, ROTATIONS_DEG)
        shortlist = select_candidates(scored, 1, MIN_SEPARATION_M)
        base = None
        for row in shortlist:
            try:
                base = refine(graph, SCALE_SHAPE, np.array([row["x"], row["y"]]),
                              row["rotation"], WIDTH_M)
            except NoRouteFoundError:
                base = None
        sweep = []
        if base is not None:
            for n in SPACING_SWEEP:
                try:
                    fitted = refine(graph, SCALE_SHAPE, base["centre_xy"],
                                    base["rotation"], WIDTH_M, points=n)
                except NoRouteFoundError:
                    continue
                if fitted is None:
                    continue
                spacing = perimeter(SCALE_SHAPE) / n * WIDTH_M
                sweep.append({"n": n, "spacing_m": spacing,
                              "distance": fitted["distance"],
                              "backtracked": fitted["metrics"]["backtracked_edges"]})
                print(f"    n={n:>4}  spacing {spacing:>4.0f} m  "
                      f"distance {fitted['distance']:.3f}", flush=True)
        scale = min(sweep, key=lambda s: s["distance"])["spacing_m"] if sweep else None
        if scale:
            print(f"    -> characteristic scale {scale:.0f} m")

        results[mode] = {"stats": stats, "fits": fits, "sweep": sweep, "scale_m": scale}

    OUT_JSON.write_text(json.dumps(results, indent=1))

    # --- comparison -------------------------------------------------------
    print("\n\n================ walk vs bike ================")
    w, b = results["walk"], results["bike"]
    print(f"{'':<24}{'walk':>12}{'bike':>12}{'ratio':>9}")
    for label, key in (("network km", "km_of_network"),
                       ("nodes", "nodes"),
                       ("median distance to it", "median_to_network_m")):
        a, c = w["stats"][key], b["stats"][key]
        print(f"{label:<24}{a:>12,.0f}{c:>12,.0f}{c / a:>9.2f}")
    if w["scale_m"] and b["scale_m"]:
        print(f"{'characteristic scale m':<24}{w['scale_m']:>12.0f}{b['scale_m']:>12.0f}"
              f"{b['scale_m'] / w['scale_m']:>9.2f}")
    ok = [s for s in SHAPES if b["fits"].get(s, {}).get("status") == "ok"]
    print(f"\nshapes still routable by bike: {len(ok)}/{len(SHAPES)}  "
          f"({', '.join(ok) if ok else 'none'})")
    dead = [s for s in SHAPES if b["fits"].get(s, {}).get("status") != "ok"]
    if dead:
        print(f"lost: {', '.join(dead)}")
    dw = [f["detour"] for f in w["fits"].values() if f.get("status") == "ok"]
    db = [f["detour"] for f in b["fits"].values() if f.get("status") == "ok"]
    if dw and db:
        print(f"detour ratio: walk {np.mean(dw):.2f}  bike {np.mean(db):.2f}")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    shapes_ok = [s for s in SHAPES if w["fits"].get(s, {}).get("status") == "ok"]
    x = np.arange(len(shapes_ok))
    for i, (mode, colour) in enumerate((("walk", "#2f6f9f"), ("bike", "#1a7f37"))):
        vals = [results[mode]["fits"].get(s, {}).get("distance", np.nan) for s in shapes_ok]
        axes[0].bar(x + (i - 0.5) * 0.38, vals, 0.38, label=mode, color=colour)
        back = [results[mode]["fits"].get(s, {}).get("backtracked", np.nan) for s in shapes_ok]
        axes[1].bar(x + (i - 0.5) * 0.38, back, 0.38, label=mode, color=colour)
    axes[0].set_ylabel("shape distance (lower is better)")
    axes[1].set_ylabel("backtracked segments")
    for ax in axes:
        ax.set_xticks(x); ax.set_xticklabels(shapes_ok, fontsize=9)
        ax.grid(axis="y", color="#dfe4e9", lw=0.7); ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.legend(fontsize=9, frameon=False)
    fig.suptitle("POC 10 — the same shapes on a network a bicycle may legally use",
                 fontsize=14)
    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nsaved {OUT_PNG}")


if __name__ == "__main__":
    main()
