"""
Regenerate `poc3_rotation_pitfall.png` — the figure documenting POC 3's
metric-gaming episode.

Both panels are fitted with the identical matcher and scored with the identical
metric. The tilted one scores BETTER on shape chamfer and looks worse, because
the metric is computed against the rotated reference and so cannot see tilt.

Run:  python make_pitfall_figure.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

from heart_route_poc import download_walk_graph
from heart_route_poc3 import (
    HEART_WIDTH_M, NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON,
    _draw_route, refine_placement,
)

# The two winners the search reported, tilted vs upright.
TILTED = (25.0382, 121.5400, 30.0)
UPRIGHT = (25.0544, 121.5378, 0.0)
OUT = Path(__file__).with_name("poc3_rotation_pitfall.png")


def main() -> None:
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)

    fig, axes = plt.subplots(1, 2, figsize=(19, 10))
    for ax, (lat, lon, rot), label in zip(
        axes, (TILTED, UPRIGHT), ("searched with tilt allowed", "searched upright")
    ):
        xy = np.array(to_proj.transform(lon, lat))
        result = refine_placement(graph, xy, rot, HEART_WIDTH_M)
        _draw_route(ax, graph, result, f"rotation {rot:+.0f}° — {label}", "#6a3d9a")

    fig.suptitle("POC 3 — the shape metric cannot tell these two apart", fontsize=14)
    fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
