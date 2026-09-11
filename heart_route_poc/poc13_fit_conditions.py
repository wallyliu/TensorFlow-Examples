"""
Fit "LIT" four ways, so a rater can settle whether the metric is inverted for text.

POC 12 found `shape_distance` scoring tilted, unreadable placements BETTER than
upright, readable ones. That is a claim about what a person sees, and so far the
only person who has looked at these four pictures is me. This produces the four
routes as images with their metric scores kept in a sidecar, for a rater who is
never shown the scores.

Run:  python poc13_fit_conditions.py
Out:  rater/lit_*.png, poc13_conditions.json
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

WORD = "LIT"
MODE = "bike"
CONDITIONS = [("outline", "free", tuple(range(0, 360, 30))),
              ("outline", "upright", (0.0,)),
              ("stroke", "free", tuple(range(0, 360, 30))),
              ("stroke", "upright", (0.0,))]
OUT_DIR = Path(__file__).with_name("rater")
OUT_JSON = Path(__file__).with_name("poc13_conditions.json")


def render(xy: np.ndarray, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    ax.plot(xy[:, 0], xy[:, 1], lw=1.5, color="#1a1a1a")
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(0.02, 0.02, 0.98, 0.98)
    fig.savefig(path, dpi=110, facecolor="white")
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    cfg = rf.MODES[MODE]
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M, mode=MODE)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    out = {}
    for style, rot_label, rotations in CONDITIONS:
        curve = mc.text_curve(WORD, style)
        name = sl.register(f"w_{style}", curve)
        n = n_min_curve(curve)
        width = n * cfg["street_scale_m"] / perimeter(curve)
        margin = max(400.0, NETWORK_HALF_SIZE_M - width * 0.75)
        centers, _, _ = build_center_grid(region, margin, GRID_STEP_M)
        scored = coarse_scan(tree, centers, name, width, rotations)
        best = None
        for row in select_candidates(scored, 3, MIN_SEPARATION_M):
            try:
                fit = refine(graph, name, np.array([row["x"], row["y"]]),
                             row["rotation"], width, points=n)
            except NoRouteFoundError:
                continue
            if fit is not None and (best is None or fit["distance"] < best["distance"]):
                best = fit
        key = f"{style}_{rot_label}"
        if best is None:
            out[key] = {"status": "no route"}
            print(f"{key}: no route")
            continue
        render(best["route_xy"], OUT_DIR / f"lit_{key}.png")
        np.save(OUT_DIR / f"lit_{key}.npy", best["route_xy"])
        out[key] = {"style": style, "rotation": rot_label, "n": n,
                    "width_m": width, "rotation_deg": float(best["rotation"]),
                    "distance": best["distance"],
                    "route_km": best["metrics"]["route_km"]}
        print(f"{key}: rotation {best['rotation']:.0f} deg, "
              f"distance {best['distance']:.3f}, {best['metrics']['route_km']:.1f} km")

    OUT_JSON.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
