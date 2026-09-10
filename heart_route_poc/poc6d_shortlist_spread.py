"""
POC 6 - record the full spread of every shape's shortlist, not just its winner.

`poc6_results.json` keeps only the best placement per shape, which is enough to
say the pipeline works but not enough to answer the question the threshold task
raises: are the differences the SEARCH ranks big enough for anyone to see? That
needs the whole shortlist, so this re-runs the search and saves every distance.

Run:  python poc6d_shortlist_spread.py
Out:  poc6d_shortlist.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from heart_route_poc import download_walk_graph
from heart_route_poc3 import (
    GRID_STEP_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON,
    build_center_grid, build_street_index, select_candidates,
)
from poc6_shapes import N_REFINE, ROTATIONS_DEG, WIDTH_M, coarse_scan, refine
from pyproj import Transformer
from shape_library import SHAPES

OUT = Path(__file__).with_name("poc6d_shortlist.json")


def main() -> None:
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)
    centers, _, _ = build_center_grid(region, NETWORK_HALF_SIZE_M - WIDTH_M * 0.75, GRID_STEP_M)

    out = {}
    for shape in SHAPES:
        scored = coarse_scan(tree, centers, shape, WIDTH_M, ROTATIONS_DEG)
        shortlist = select_candidates(scored, N_REFINE, MIN_SEPARATION_M)
        distances = []
        for row in shortlist:
            fitted = refine(graph, shape, np.array([row["x"], row["y"]]), row["rotation"], WIDTH_M)
            if fitted is not None:
                distances.append(round(fitted["distance"], 4))
        out[shape] = sorted(distances)
        print(f"{shape:<10} n={len(distances)}  best {min(distances):.3f}  "
              f"worst {max(distances):.3f}  spread {max(distances) - min(distances):.3f}",
              flush=True)

    OUT.write_text(json.dumps(out, indent=1))
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
