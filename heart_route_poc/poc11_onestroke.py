"""
Does joining contours with short links actually unblock text?

The multi-contour problem was logged as the hard blocker for text-to-shape: LOVE
is 5 closed curves, TAIPEI is 8, and every metric and search stage in this
project assumes one. The user's suggestion was to stop treating that as a
topology problem - link the pieces with the shortest lines and ride the links
twice, and it is one curve again.

Measured here: how much perimeter the links cost, what n_min the merged curve
needs, and what that implies for distance. The links are cheap. The distance is
not, and for a different reason than the contour count.

Run:  python poc11_onestroke.py
Out:  poc11_onestroke.png, poc11_onestroke.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import route_feasibility as rf
from multi_contour import densify, merge, text_contours
from shape_metrics import resample_closed, shape_distance

WORDS = ["LIT", "LOVE", "TAIPEI"]
TOLERANCE = rf.SAMPLING_TOLERANCE
OUT_PNG = Path(__file__).with_name("poc11_onestroke.png")
OUT_JSON = Path(__file__).with_name("poc11_onestroke.json")


def perimeter(curve: np.ndarray) -> float:
    return float(np.hypot(*np.diff(np.vstack([curve, curve[:1]]), axis=0).T).sum())


def n_min_curve(curve: np.ndarray, ceiling: int = 400) -> int:
    """route_feasibility.n_min, for a curve that is not in the shape library."""
    dense = resample_closed(curve, 4000)
    grid = list(range(4, ceiling + 1, 4))
    loss = {n: shape_distance(resample_closed(curve, n), dense) for n in grid}
    for n in grid:
        if all(loss[m] < TOLERANCE for m in grid if m >= n):
            return n
    return ceiling


def main() -> None:
    cfg = rf.MODES["bike"]
    results = {}
    fig, axes = plt.subplots(1, len(WORDS), figsize=(5 * len(WORDS), 4.2))

    print(f"{'word':8}{'contours':>9}{'links':>7}{'link %':>8}{'n_min':>7}"
          f"{'width km':>10}{'bike km':>9}{'walk km':>9}")
    for ax, word in zip(np.atleast_1d(axes), WORDS):
        contours = [densify(p, 0.01) for p in text_contours(word)]
        curve, link_len, edges = merge(contours)
        span = curve.max(axis=0) - curve.min(axis=0)
        curve = (curve - curve.min(axis=0) - span / 2) / span[0]

        p = perimeter(curve)
        link_share = 2 * link_len / span[0] / p
        n = n_min_curve(curve)
        width_km = n * cfg["street_scale_m"] / p / 1000.0
        bike_km = n * cfg["street_scale_m"] * cfg["detour"] / 1000.0
        walk_km = (n * rf.MODES["walk"]["street_scale_m"]
                   * rf.MODES["walk"]["detour"] / 1000.0)

        results[word] = {"contours": len(contours), "links": len(edges),
                         "link_share": link_share, "perimeter": p, "n_min": n,
                         "width_km": width_km, "bike_km": bike_km,
                         "walk_km": walk_km,
                         "height_km": width_km * span[1] / span[0]}
        print(f"{word:8}{len(contours):9d}{len(edges):7d}{link_share * 100:7.1f}%"
              f"{n:7d}{width_km:10.1f}{bike_km:9.1f}{walk_km:9.1f}")

        ax.plot(curve[:, 0], curve[:, 1], lw=1.1, color="#2b6cb0")
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"{word}: {len(contours)} contours joined into 1 closed curve\n"
                     f"links {link_share * 100:.1f}% of perimeter, n_min {n}, "
                     f"min bike {bike_km:.0f} km", fontsize=10)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=130)
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
