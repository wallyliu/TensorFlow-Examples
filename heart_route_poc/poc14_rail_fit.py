"""
Fit "LIT" again with the links moved off the letters.

POC 13's rater read the upright outline route as "UT" and said the links sat too
close to the letters to tell them apart. That is a fair description of what
nearest-point linking does: it attaches two letters at the two points where they
most nearly touch, which is exactly where a reader needs space.

This fits the rail alternative - every letter drops a stem to a line below the
word, the stems joined along it, so the whole connecting structure reads as an
underline. Same word, same network, same upright constraint; only the links
move.

Run:  python poc14_rail_fit.py
Out:  rater/lit_*_rail.png, poc14_rail.json
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
from poc13_fit_conditions import render
from route_export import write_gpx

WORD = "LIT"
MODE = "bike"
ROTATIONS_DEG = (0.0,)
STYLES = ["outline", "stroke"]
OUT_DIR = Path(__file__).with_name("rater")
GPX_DIR = Path(__file__).with_name("gpx")
OUT_JSON = Path(__file__).with_name("poc14_rail.json")


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    GPX_DIR.mkdir(exist_ok=True)
    cfg = rf.MODES[MODE]
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M, mode=MODE)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    out = {}
    for style in STYLES:
        curve = mc.text_curve(WORD, style, link="rail")
        name = sl.register(f"w_{style}_rail", curve)
        n = n_min_curve(curve)
        width = n * cfg["street_scale_m"] / perimeter(curve)
        print(f"\n=== {WORD} {style} rail: n_min {n}, width {width:.0f} m, "
              f"predicted {n * cfg['street_scale_m'] * cfg['detour'] / 1000:.1f} km")

        margin = max(400.0, NETWORK_HALF_SIZE_M - width * 0.75)
        centers, _, _ = build_center_grid(region, margin, GRID_STEP_M)
        scored = coarse_scan(tree, centers, name, width, ROTATIONS_DEG)
        if not np.isfinite(scored["score"]).any():
            out[style] = {"status": "no placement"}
            print("  no placement")
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
            out[style] = {"status": "no route"}
            print("  no route")
            continue
        key = f"{style}_rail"
        render(best["route_xy"], OUT_DIR / f"lit_{key}.png")
        np.save(OUT_DIR / f"lit_{key}.npy", best["route_xy"])
        write_gpx(best, graph.graph["crs"], GPX_DIR / f"word_lit_{key}.gpx",
                  f"{WORD} ({style}, rail)", WORD, MODE)
        out[key] = {"style": style, "link": "rail", "n": n, "width_m": width,
                    "distance": best["distance"],
                    "route_km": best["metrics"]["route_km"]}
        print(f"  distance {best['distance']:.3f}, {best['metrics']['route_km']:.1f} km")

    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
