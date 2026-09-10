"""
POC 4, part 2 - does the new ruler change any real decision?

A metric that wins a battery of synthetic deformations has proved nothing until
it changes an actual answer. This re-scores real Taipei routes with both the
incumbent metric and the winner, and checks three things:

  1. the rotation pitfall - POC 3's tilted and upright winners scored 18 m each
     under the incumbent, an exact tie it had no way to break;
  2. whether the two metrics rank POC 3's shortlist differently at all;
  3. whether the route the new metric prefers actually looks better.

Run:  python poc4_apply_to_routes.py
Out:  poc4_route_ranking.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer
from scipy.stats import spearmanr

from heart_route_poc import download_walk_graph, generate_heart_points
from heart_route_poc3 import (
    GRID_STEP_M, HEART_WIDTH_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M,
    ROTATIONS_DEG, SEARCH_LAT, SEARCH_LON, _draw_route, build_center_grid,
    build_street_index, coarse_scan, refine_placement, select_candidates,
)
from shape_metrics import chamfer_placed, chamfer_upright, procrustes_upright

N_PLACEMENTS = 12
OUT_PNG = Path(__file__).with_name("poc4_route_ranking.png")

# POC 3's two winners: the tilted one the rotation search preferred, and the
# upright one found once rotation was locked out.
PITFALL_TILTED = (25.0382, 121.5400, 30.0)
PITFALL_UPRIGHT = (25.0544, 121.5378, 0.0)


def upright_template() -> np.ndarray:
    """The canonical heart the upright metrics score against, in metres."""
    return generate_heart_points(2048) * HEART_WIDTH_M


def score(result: dict) -> dict[str, float]:
    template = upright_template()
    return {
        "chamfer_placed": chamfer_placed(result["route_xy"], result["reference"]),
        "chamfer_upright": chamfer_upright(result["route_xy"], template),
        "procrustes_upright": procrustes_upright(result["route_xy"], template),
    }


def main() -> None:
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    crs = graph.graph["crs"]
    to_proj = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

    # --- 1. the rotation pitfall -------------------------------------------
    print("1. The rotation pitfall, re-scored\n")
    pitfall = {}
    for label, (lat, lon, rot) in (("tilted +30°", PITFALL_TILTED),
                                   ("upright", PITFALL_UPRIGHT)):
        xy = np.array(to_proj.transform(lon, lat))
        result = refine_placement(graph, xy, rot, HEART_WIDTH_M)
        pitfall[label] = (result, score(result))

    header = f"{'route':<16}{'chamfer_placed':>18}{'chamfer↑':>14}{'procrustes↑':>16}"
    print(header)
    print("-" * len(header))
    for label, (_, s) in pitfall.items():
        print(f"{label:<16}{s['chamfer_placed']:>18.1f}{s['chamfer_upright']:>14.3f}"
              f"{s['procrustes_upright']:>16.3f}")
    gap = {m: pitfall["tilted +30°"][1][m] / pitfall["upright"][1][m]
           for m in ("chamfer_placed", "chamfer_upright", "procrustes_upright")}
    print("\ntilted ÷ upright: " + "  ".join(f"{m}={v:.2f}x" for m, v in gap.items()))
    print("(1.00x means the metric cannot tell them apart)")

    # --- 2. does the ranking change? ---------------------------------------
    print(f"\n\n2. Re-ranking {N_PLACEMENTS} real placements from POC 3's search\n")
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)
    centers, _, _ = build_center_grid(
        region, NETWORK_HALF_SIZE_M - HEART_WIDTH_M * 0.75, GRID_STEP_M
    )
    scored_grid = coarse_scan(tree, centers, HEART_WIDTH_M, rotations=ROTATIONS_DEG)
    shortlist = select_candidates(scored_grid, N_PLACEMENTS, MIN_SEPARATION_M)

    results, rows = [], []
    for rank, row in enumerate(shortlist, start=1):
        result = refine_placement(graph, np.array([row["x"], row["y"]]),
                                  row["rotation"], HEART_WIDTH_M)
        if result is None:
            continue
        s = score(result)
        result["scores"] = s
        results.append(result)
        rows.append(s)
        print(f"  placement {rank:2d}: chamfer_placed {s['chamfer_placed']:5.1f} m   "
              f"procrustes↑ {s['procrustes_upright']:.3f}   "
              f"backtracked {result['metrics']['backtracked_edges']:2d}")

    old = np.array([r["chamfer_placed"] for r in rows])
    new = np.array([r["procrustes_upright"] for r in rows])
    rho, p = spearmanr(old, new)
    print(f"\nSpearman(chamfer_placed, procrustes↑) = {rho:+.3f}  (p={p:.3f})")

    best_old = int(np.argmin(old))
    best_new = int(np.argmin(new))
    print(f"chamfer_placed picks placement #{best_old + 1}; "
          f"procrustes↑ picks placement #{best_new + 1}"
          f"{'  — same route' if best_old == best_new else '  — DIFFERENT route'}")

    # --- 3. show the disagreement ------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(27, 9.5))
    _draw_route(axes[0], graph, pitfall["tilted +30°"][0],
                f"POC 3's tilted winner\nprocrustes↑ "
                f"{pitfall['tilted +30°'][1]['procrustes_upright']:.3f}", "#e8443a")
    _draw_route(axes[1], graph, pitfall["upright"][0],
                f"POC 3's upright winner\nprocrustes↑ "
                f"{pitfall['upright'][1]['procrustes_upright']:.3f}", "#1a7f37")
    _draw_route(axes[2], graph, results[best_new],
                f"best of {len(results)} by procrustes↑\nprocrustes↑ "
                f"{new[best_new]:.3f}", "#6a3d9a")
    fig.suptitle("POC 4 — the incumbent metric scored the first two identically", fontsize=15)
    fig.savefig(OUT_PNG, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nsaved {OUT_PNG}")


if __name__ == "__main__":
    main()
