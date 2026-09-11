"""
POC 7 - how complex a shape can this pipeline draw?

POC 6 ran four shapes and concluded the pipeline is not a heart trick. All four
were simple. A T-rex silhouette has concave features at very different scales -
a mouth notch, an armpit, a gap between two legs, the underside of a tail - and
it exposes two limits POC 6 never reached.

LIMIT 1, TOPOLOGY. The real sprite has an eye, and an eye is a hole. Every stage
here assumes a single closed curve, so a shape with a hole cannot be expressed
at all. Dropping the eye to get a runnable shape is the finding, not a
workaround.

LIMIT 2, SAMPLING. POC 6 used n=40 contour points for every shape. Perimeters
differ, so that was never the same sampling density: at 2 km wide it is one
sample every 160 m for a heart and every 244 m for a T-rex. The gap between the
dinosaur's legs is about 160 m - which the street network can render, since its
own limit is nearer 50 m - but a sampler taking one point every 244 m cannot
even see it. For complex shapes the bottleneck is the contour sampler, not the
streets, and POC 6's comparison quietly penalised its most complex shapes.

So this measures the T-rex against contour resolution, and re-runs POC 6's four
shapes at MATCHED sampling density to see how much of their ranking was an
artifact of the convention.

Run:  python poc7_trex.py
Out:  poc7_trex.png, poc7_results.json
"""

from __future__ import annotations

import json
import time
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
from poc6_shapes import ROTATIONS_DEG, WIDTH_M, coarse_scan, refine
from shape_library import SHAPES, resample_by_arclength

SEARCH_POINTS = 80          # used to find the placement
SWEEP = [40, 61, 80, 120, 160]
HEART_SPACING = None        # filled in at run time: the density POC 6 gave a heart
N_REFINE = 6
OUT_PNG = Path(__file__).with_name("poc7_trex.png")
OUT_JSON = Path(__file__).with_name("poc7_results.json")


def perimeter(shape: str) -> float:
    pts = resample_by_arclength(shape, 4000)
    closed = np.vstack([pts, pts[:1]])
    return float(np.hypot(*np.diff(closed, axis=0).T).sum())


def main() -> None:
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    to_wgs = Transformer.from_crs(graph.graph["crs"], "EPSG:4326", always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)
    centers, _, _ = build_center_grid(region, NETWORK_HALF_SIZE_M - WIDTH_M * 0.75, GRID_STEP_M)

    heart_spacing = perimeter("heart") / 40
    results = {"heart_spacing": heart_spacing, "trex_sweep": [], "matched": []}

    # --- find a placement for the T-rex ------------------------------------
    print("=== T-rex: searching for a placement ===")
    scored = coarse_scan(tree, centers, "trex", WIDTH_M, ROTATIONS_DEG)
    shortlist = select_candidates(scored, N_REFINE, MIN_SEPARATION_M)
    best = None
    for rank, row in enumerate(shortlist, start=1):
        fitted = refine(graph, "trex", np.array([row["x"], row["y"]]), row["rotation"],
                        WIDTH_M, points=SEARCH_POINTS)
        if fitted is None:
            print(f"  #{rank}: infeasible")
            continue
        print(f"  #{rank}: distance {fitted['distance']:.3f}  "
              f"{fitted['metrics']['route_km']:.2f} km  backtracked "
              f"{fitted['metrics']['backtracked_edges']}", flush=True)
        if best is None or fitted["distance"] < best["distance"]:
            best = fitted

    lat, lon = to_wgs.transform(best["centre_xy"][0], best["centre_xy"][1])[::-1]
    print(f"  best at {lat:.4f}, {lon:.4f}, rotation {best['rotation']:+.0f}°")

    # --- how much does contour resolution matter? --------------------------
    print("\n=== T-rex: same placement, varying contour resolution ===")
    print(f"{'n':>5}{'spacing @2km':>15}{'distance':>11}{'route km':>10}{'backtrk':>9}{'time':>8}")
    fits = {}
    for n in SWEEP:
        t0 = time.perf_counter()
        fitted = refine(graph, "trex", best["centre_xy"], best["rotation"], WIDTH_M, points=n)
        if fitted is None:
            print(f"{n:>5}  infeasible")
            continue
        fits[n] = fitted
        spacing = perimeter("trex") / n * WIDTH_M
        results["trex_sweep"].append({
            "n": n, "spacing_m": spacing, "distance": fitted["distance"],
            "route_km": fitted["metrics"]["route_km"],
            "backtracked": fitted["metrics"]["backtracked_edges"]})
        print(f"{n:>5}{spacing:>13.0f} m{fitted['distance']:>11.3f}"
              f"{fitted['metrics']['route_km']:>10.2f}"
              f"{fitted['metrics']['backtracked_edges']:>9}"
              f"{time.perf_counter() - t0:>7.0f}s", flush=True)

    # --- re-run POC 6's shapes at MATCHED sampling density -----------------
    print(f"\n=== POC 6's shapes at matched density ({heart_spacing:.3f} of width) ===")
    print(f"{'shape':<10}{'n used':>8}{'POC 6 n':>9}{'distance':>11}{'backtrk':>9}")
    poc6 = {r["shape"]: r for r in json.loads(
        (Path(__file__).with_name("poc6_results.json")).read_text())}
    for shape in SHAPES:
        if shape == "trex":
            continue
        n = max(8, round(perimeter(shape) / heart_spacing))
        centre = np.array(to_proj.transform(poc6[shape]["lon"], poc6[shape]["lat"]))
        fitted = refine(graph, shape, centre, poc6[shape]["rotation"], WIDTH_M, points=n)
        if fitted is None:
            continue
        results["matched"].append({
            "shape": shape, "n": n, "distance": fitted["distance"],
            "backtracked": fitted["metrics"]["backtracked_edges"],
            "poc6_distance": poc6[shape]["distance"],
            "poc6_backtracked": poc6[shape]["backtracked"]})
        print(f"{shape:<10}{n:>8}{40:>9}{fitted['distance']:>11.3f}"
              f"{fitted['metrics']['backtracked_edges']:>9}"
              f"   (POC 6: {poc6[shape]['distance']:.3f}, "
              f"{poc6[shape]['backtracked']} backtracked)", flush=True)

    results["best"] = {"lat": float(lat), "lon": float(lon),
                       "rotation": float(best["rotation"])}
    OUT_JSON.write_text(json.dumps(results, indent=1))

    # --- picture -----------------------------------------------------------
    show = [n for n in (40, 80, 160) if n in fits]
    fig, axes = plt.subplots(1, len(show), figsize=(6.2 * len(show), 6.6))
    axes = np.atleast_1d(axes)
    for ax, n in zip(axes, show):
        fitted = fits[n]
        ox.plot_graph(graph, ax=ax, node_size=0, edge_color="#dddddd", edge_linewidth=0.35,
                      bgcolor="white", show=False, close=False)
        ref = fitted["reference"]
        ax.plot(ref[:, 0], ref[:, 1], color="#c94a3f", lw=1.5, ls="--", label="ideal", zorder=3)
        xy = fitted["route_xy"]
        ax.plot(xy[:, 0], xy[:, 1], color="#1f5f8b", lw=2.3, label="walking route", zorder=4)
        margin = 320.0
        ax.set_xlim(ref[:, 0].min() - margin, ref[:, 0].max() + margin)
        ax.set_ylim(ref[:, 1].min() - margin, ref[:, 1].max() + margin)
        m = fitted["metrics"]
        ax.set_title(f"{n} contour points — one every "
                     f"{perimeter('trex') / n * WIDTH_M:.0f} m\n"
                     f"distance {fitted['distance']:.3f} · {m['route_km']:.2f} km · "
                     f"{m['backtracked_edges']} backtracked", fontsize=10)
        ax.legend(loc="upper right", fontsize=8)
    fig.suptitle("POC 7 — a T-rex on Taipei streets, at three contour resolutions",
                 fontsize=14)
    fig.savefig(OUT_PNG, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nsaved {OUT_PNG}")


if __name__ == "__main__":
    main()
