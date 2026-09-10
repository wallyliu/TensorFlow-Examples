"""
POC 5, step 4 - re-run POC 3's location search under the corrected metric.

POC 4 measured the incumbent metric and the new one at rho = -0.007 on real
routes: unrelated. Every placement decision in POC 1-3 was therefore made with
a ruler that does not measure the goal, and this re-runs the search under the
new one.

It also asks the question POC 3's validation cannot answer any more. POC 3
showed its cheap stage-1 filter predicts the final score at rho = +0.76 - but
that was measured against chamfer. If the two metrics are unrelated, stage 1's
usefulness is unproven under the new objective, and the whole two-stage design
may rest on nothing. Same experiment, new yardstick.

Run:  python poc5_research.py
Out:  poc5_research.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
from scipy.stats import spearmanr

from heart_route_poc import download_walk_graph, generate_heart_points
from heart_route_poc3 import (
    GRID_STEP_M, HEART_WIDTH_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M,
    ROTATIONS_DEG, SEARCH_LAT, SEARCH_LON, build_center_grid, build_street_index,
    coarse_scan, refine_placement, select_candidates,
)
from shape_metrics import chamfer_placed, chamfer_upright, procrustes_upright_fft

N_SAMPLE = 25
OUT_JSON = Path(__file__).with_name("poc5_research.json")
POC3_WINNER = (25.0544, 121.5378)


def main() -> None:
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    crs = graph.graph["crs"]
    to_proj = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    template = generate_heart_points(2048) * HEART_WIDTH_M

    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)
    centers, _, _ = build_center_grid(
        region, NETWORK_HALF_SIZE_M - HEART_WIDTH_M * 0.75, GRID_STEP_M
    )
    scored = coarse_scan(tree, centers, HEART_WIDTH_M, rotations=ROTATIONS_DEG)
    viable = scored[np.isfinite(scored["score"])]

    top = select_candidates(scored, N_SAMPLE, MIN_SEPARATION_M)
    rng = np.random.default_rng(5)
    rand = viable[rng.choice(len(viable), N_SAMPLE, replace=False)]

    def evaluate(rows, tag):
        out = []
        for i, row in enumerate(rows, start=1):
            result = refine_placement(graph, np.array([row["x"], row["y"]]),
                                      row["rotation"], HEART_WIDTH_M)
            if result is None:
                print(f"  {tag} {i}: infeasible", flush=True)
                continue
            lon, lat = to_wgs.transform(row["x"], row["y"])
            out.append({
                "tag": tag, "lat": float(lat), "lon": float(lon),
                "rotation": float(row["rotation"]), "coarse": float(row["score"]),
                "chamfer_placed": chamfer_placed(result["route_xy"], result["reference"]),
                "chamfer_upright": chamfer_upright(result["route_xy"], template),
                "procrustes": procrustes_upright_fft(result["route_xy"], template),
                "backtracked": int(result["metrics"]["backtracked_edges"]),
                "route_km": float(result["metrics"]["route_km"]),
            })
            print(f"  {tag} {i}/{len(rows)}: coarse {row['score']:5.1f} -> "
                  f"procrustes {out[-1]['procrustes']:.3f}", flush=True)
        return out

    rows = evaluate(top, "coarse-top") + evaluate(rand, "random")

    coarse = np.array([r["coarse"] for r in rows])
    proc = np.array([r["procrustes"] for r in rows])
    cham = np.array([r["chamfer_placed"] for r in rows])

    result = {
        "rows": rows,
        "spearman_coarse_vs_procrustes": list(map(float, spearmanr(coarse, proc))),
        "spearman_coarse_vs_chamfer": list(map(float, spearmanr(coarse, cham))),
        "spearman_chamfer_vs_procrustes": list(map(float, spearmanr(cham, proc))),
    }
    OUT_JSON.write_text(json.dumps(result, indent=1))

    print("\n--- does stage 1 still predict the final score? ---")
    print(f"coarse vs chamfer_placed (POC 3's claim): rho={result['spearman_coarse_vs_chamfer'][0]:+.3f} "
          f"p={result['spearman_coarse_vs_chamfer'][1]:.4f}")
    print(f"coarse vs procrustes (new objective)    : rho={result['spearman_coarse_vs_procrustes'][0]:+.3f} "
          f"p={result['spearman_coarse_vs_procrustes'][1]:.4f}")
    print(f"chamfer vs procrustes                   : rho={result['spearman_chamfer_vs_procrustes'][0]:+.3f} "
          f"p={result['spearman_chamfer_vs_procrustes'][1]:.4f}")

    for tag in ("coarse-top", "random"):
        group = [r for r in rows if r["tag"] == tag]
        vals = np.array([r["procrustes"] for r in group])
        print(f"\n{tag:<11} procrustes mean {vals.mean():.3f}  min {vals.min():.3f}  "
              f"p25 {np.percentile(vals, 25):.3f}")

    best = min(rows, key=lambda r: r["procrustes"])
    print(f"\nbest under procrustes: {best['lat']:.4f}, {best['lon']:.4f} "
          f"({best['tag']}, procrustes {best['procrustes']:.3f}, "
          f"chamfer_placed {best['chamfer_placed']:.1f} m)")
    print(f"POC 3's winner was    : {POC3_WINNER[0]:.4f}, {POC3_WINNER[1]:.4f}")
    print(f"saved {OUT_JSON}")


if __name__ == "__main__":
    main()
