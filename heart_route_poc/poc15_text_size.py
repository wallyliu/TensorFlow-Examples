"""
Is it the links, or is it the size?

POC 14 left two explanations for why nobody can read these word routes. Three
raters reading the same route as "UT" points at the links between letters.
Nobody reading any version at all leaves size open. The two make opposite
predictions about what happens when the same word is drawn twice as large, so
this draws it.

LIT, outline, upright, on a bike network widened to 14 km so the big one fits:

  small   4.5 km wide - the width POC 12 used, the one raters read as "UT"
  large   9.1 km wide - the same word, every letter feature spanning twice as
          many streets, at roughly 59 km of riding

If size is the problem the large one should read. If the links are the problem
it should fail the same way, because the links scale with everything else.

Run:  python poc15_text_size.py
Out:  poc15_text_size.png, poc15_text_size.json, rater/size_*.png
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
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M, SEARCH_LAT,
                              SEARCH_LON, build_center_grid, build_street_index,
                              select_candidates)
from poc6_shapes import coarse_scan, refine
from poc11_onestroke import n_min_curve, perimeter
from poc15_big_network import HALF_SIZE_M
from route_export import write_gpx

WORD = "LIT"
MODE = "bike"
ROTATIONS_DEG = (0.0,)          # text is not rotation-invariant; see POC 12
SCALES = {"small": 1.0, "large": 2.0}
OUT_PNG = Path(__file__).with_name("poc15_text_size.png")
OUT_JSON = Path(__file__).with_name("poc15_text_size.json")
RATER = Path(__file__).with_name("rater")


def main() -> None:
    RATER.mkdir(exist_ok=True)
    cfg = rf.MODES[MODE]
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, HALF_SIZE_M, mode=MODE)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    curve = mc.text_curve(WORD, "outline")
    name = sl.register(f"word_{WORD.lower()}_outline", curve)
    base_n = n_min_curve(curve)
    p = perimeter(curve)

    results, routes = {}, {}
    for tag, factor in SCALES.items():
        width = factor * base_n * cfg["street_scale_m"] / p
        # Anchors stay one street scale apart, so the bigger word is sampled
        # proportionally more finely rather than more coarsely.
        n = max(base_n, int(round(p * width / cfg["street_scale_m"])))
        print(f"\n=== {tag}: {width / 1000:.1f} km wide, {n} points, "
              f"predicted {n * cfg['street_scale_m'] * cfg['detour'] / 1000:.0f} km")

        margin = max(500.0, HALF_SIZE_M - width * 0.75)
        centers, _, _ = build_center_grid(region, margin, GRID_STEP_M)
        scored = coarse_scan(tree, centers, name, width, ROTATIONS_DEG)
        if not np.isfinite(scored["score"]).any():
            results[tag] = {"status": "no placement"}
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
            results[tag] = {"status": "no route"}
            print("  no route")
            continue

        routes[tag] = best["route_xy"]
        np.save(RATER / f"size_{tag}.npy", best["route_xy"])
        write_gpx(best, graph.graph["crs"],
                  Path(__file__).with_name("gpx") / f"word_lit_{tag}.gpx",
                  f"{WORD} ({tag})", WORD, MODE)
        results[tag] = {"status": "ok", "width_m": width, "points": n,
                        "distance": best["distance"],
                        "route_km": best["metrics"]["route_km"]}
        print(f"  distance {best['distance']:.3f}, "
              f"{best['metrics']['route_km']:.1f} km")

    fig, axes = plt.subplots(1, len(SCALES), figsize=(6 * len(SCALES), 5))
    for ax, tag in zip(np.atleast_1d(axes), SCALES):
        r = results.get(tag, {})
        if tag in routes:
            xy = routes[tag]
            ax.plot(xy[:, 0], xy[:, 1], lw=1.4, color="#1a1a1a")
            ax.set_title(f"{tag} · {r['width_m'] / 1000:.1f} km wide · "
                         f"{r['points']} pts\n{r['route_km']:.0f} km · "
                         f"shape distance {r['distance']:.3f}", fontsize=10)
            fig2, ax2 = plt.subplots(figsize=(5.2, 5.2))
            ax2.plot(xy[:, 0], xy[:, 1], lw=1.5, color="#1a1a1a")
            ax2.set_aspect("equal")
            ax2.axis("off")
            fig2.subplots_adjust(0.02, 0.02, 0.98, 0.98)
            fig2.savefig(RATER / f"size_{tag}.png", dpi=110, facecolor="white")
            plt.close(fig2)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(f'"{WORD}" at two sizes on the same bike network', fontsize=12)
    fig.subplots_adjust(top=0.8, wspace=0.08, left=0.03, right=0.97, bottom=0.03)
    fig.savefig(OUT_PNG, dpi=140)
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
