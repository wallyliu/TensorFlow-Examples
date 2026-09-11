"""
Ride a word, and find out the metric has been wrong about text all along.

POC 12's first half compared the two letter styles on paper. This half fits
"LIT" to Taipei's bike network in both, and turned up something neither the
paper comparison nor any earlier POC could have: **rotation invariance, which
POC 5's raters endorsed and POC 6 built the search around, is wrong for text.**

A heart tilted 40 degrees is still a heart, and a rater said so. A word tilted
40 degrees is not a word. With rotation free, the search found tilted placements
and the metric scored them WELL - outline 0.066, stroke 0.124 - while neither is
readable as LIT at all. Forcing upright produced routes that do read as letters
and the metric scored them WORSE: 0.114 and 0.164.

So for text the metric is not merely insensitive, it is inverted: it prefers the
unreadable fit. Rotation has to be a constraint supplied with the shape, not a
free parameter, and the metric owes text an orientation term it does not have.

Run:  python poc12_word_routes.py
Out:  poc12_word_routes.png, poc12_word_routes.json, gpx/word_lit_*.gpx
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

import multi_contour as mc
import route_feasibility as rf
import shape_library as sl
from heart_route_poc import download_walk_graph
from heart_route_poc2 import NoRouteFoundError
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M,
                              SEARCH_LAT, SEARCH_LON, build_center_grid,
                              build_street_index, select_candidates)
from poc6_shapes import coarse_scan, refine
from poc11_onestroke import n_min_curve, perimeter
from route_export import write_gpx

WORD = "LIT"
STYLES = ["outline", "stroke"]
ROTATIONS_DEG = (0.0,)      # see module docstring - text is not rotation-invariant
MODE = "bike"
GPX_DIR = Path(__file__).with_name("gpx")
OUT_PNG = Path(__file__).with_name("poc12_word_routes.png")
OUT_JSON = Path(__file__).with_name("poc12_word_routes.json")


def main() -> None:
    cfg = rf.MODES[MODE]
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M, mode=MODE)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    GPX_DIR.mkdir(exist_ok=True)
    results, routes = {}, {}
    for style in STYLES:
        curve = mc.text_curve(WORD, style)
        name = sl.register(f"word_{WORD.lower()}_{style}", curve)
        n = n_min_curve(curve)
        width = n * cfg["street_scale_m"] / perimeter(curve)
        print(f"\n=== {WORD} {style}: n_min {n}, width {width:.0f} m, "
              f"predicted {n * cfg['street_scale_m'] * cfg['detour'] / 1000:.1f} km")

        margin = max(400.0, NETWORK_HALF_SIZE_M - width * 0.75)
        centers, _, _ = build_center_grid(region, margin, GRID_STEP_M)
        scored = coarse_scan(tree, centers, name, width, ROTATIONS_DEG)
        if not np.isfinite(scored["score"]).any():
            results[style] = {"status": "no placement"}
            continue

        best = None
        for row in select_candidates(scored, 3, MIN_SEPARATION_M):
            try:
                fit = refine(graph, name, np.array([row["x"], row["y"]]),
                             row["rotation"], width, points=n)
            except NoRouteFoundError:
                continue
            if fit is not None and (best is None or fit["distance"] < best["distance"]):
                best = fit
        if best is None:
            results[style] = {"status": "no route"}
            continue

        write_gpx(best, graph.graph["crs"],
                  GPX_DIR / f"word_{WORD.lower()}_{style}.gpx",
                  f"{WORD} ({style})", WORD, MODE)
        routes[style] = best["route_xy"]
        results[style] = {"status": "ok", "n_min": n, "width_m": width,
                          "distance": best["distance"],
                          "route_km": best["metrics"]["route_km"]}
        print(f"  distance {best['distance']:.3f}, {best['metrics']['route_km']:.1f} km")

    fig, axes = plt.subplots(1, len(STYLES), figsize=(6 * len(STYLES), 5))
    for ax, style in zip(np.atleast_1d(axes), STYLES):
        r = results[style]
        if style in routes:
            xy = routes[style]
            ax.plot(xy[:, 0], xy[:, 1], lw=1.3, color="#2b6cb0")
            ax.set_title(f"{style}, upright · {r['width_m'] / 1000:.1f} km wide · "
                         f"{r['n_min']} pts\n{r['route_km']:.1f} km · "
                         f"shape distance {r['distance']:.3f}", fontsize=10)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(f'"{WORD}" ridden on Taipei\'s bike network', fontsize=12)
    fig.subplots_adjust(top=0.8, wspace=0.08, left=0.03, right=0.97, bottom=0.03)
    fig.savefig(OUT_PNG, dpi=140)
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
