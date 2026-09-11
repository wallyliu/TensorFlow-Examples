"""
Why the triangle comes out ugly, and whether corner-weighted sampling fixes it.

The user's complaint, and the metric agrees with them: the triangle at 8 km
scores 0.127, above the ~0.10 at which POC 6's raters reliably see a
difference, while the heart at the same distance scores 0.079.

The suspicion is the sampling. Anchors are laid down at equal ARC LENGTH, which
spends them evenly along the outline. A heart's information is spread evenly
along its outline, so that is the right thing to do. A triangle's information is
three corners and nothing else: equal spacing puts most anchors in the middle of
long straight sides where the route was never going to go wrong, and leaves the
corners - the only part that says "triangle" - to fall wherever they land.

    density(s)  proportional to  (1 - mix) + mix * |curvature(s)| / mean|curvature|

mix=0 is the current behaviour. mix=1 places anchors purely by how sharply the
outline is turning. This sweeps it, on the shapes the library already has, with
no map involved: the question is first whether a corner-weighted polygon
represents its shape better than an arc-length one at the same point count.

Run:  python poc16_corners.py
Out:  poc16_corners.png, poc16_corners.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from shape_library import SHAPES, resample_by_arclength
from shape_metrics import shape_distance

DENSE = 4000
SHAPES_TESTED = ["triangle", "star5", "heart", "crescent"]
MIXES = [0.0, 0.25, 0.5, 0.75, 1.0]
POINTS = [12, 16, 21, 28, 40]
OUT_PNG = Path(__file__).with_name("poc16_corners.png")
OUT_JSON = Path(__file__).with_name("poc16_corners.json")


def curvature(xy: np.ndarray) -> np.ndarray:
    """Turn per unit length at each point, by central difference."""
    closed = np.vstack([xy[-1:], xy, xy[:1]])
    d1 = closed[2:] - closed[:-2]
    heading = np.arctan2(d1[:, 1], d1[:, 0])
    turn = np.diff(np.concatenate([heading[-1:], heading]))
    turn = (turn + np.pi) % (2 * np.pi) - np.pi
    step = np.hypot(*np.diff(np.vstack([xy, xy[:1]]), axis=0).T)
    return np.abs(turn) / np.maximum(step, 1e-12)


def resample_weighted(shape: str, n: int, mix: float) -> np.ndarray:
    """
    Sample n points along the outline, biased toward where it turns.

    Implemented as a change of variable: integrate the density along the
    outline to get a monotone coordinate, then take n equally spaced values of
    THAT and map them back. Equal spacing in the new coordinate is
    density-proportional spacing in arc length.
    """
    dense = resample_by_arclength(shape, DENSE)
    if mix <= 0:
        return resample_by_arclength(shape, n)
    k = curvature(dense)
    k = np.minimum(k, np.percentile(k, 99))          # one cusp must not take every point
    weight = (1 - mix) + mix * k / max(k.mean(), 1e-12)
    cumulative = np.concatenate([[0.0], np.cumsum(weight)])
    targets = np.linspace(0.0, cumulative[-1], n, endpoint=False)
    idx = np.searchsorted(cumulative, targets).clip(0, DENSE - 1)
    return dense[idx]


def main() -> None:
    results = {}
    print(f"{'shape':<10}{'n':>4}" + "".join(f"{'mix ' + str(m):>10}" for m in MIXES))
    for shape in SHAPES_TESTED:
        reference = resample_by_arclength(shape, DENSE)
        results[shape] = {}
        for n in POINTS:
            row = []
            for mix in MIXES:
                d = shape_distance(resample_weighted(shape, n, mix), reference)
                row.append(d)
            results[shape][n] = dict(zip(map(str, MIXES), row))
            best = MIXES[int(np.argmin(row))]
            print(f"{shape:<10}{n:>4}" + "".join(f"{v:10.3f}" for v in row)
                  + f"   best mix {best}")

    fig, axes = plt.subplots(1, len(SHAPES_TESTED),
                             figsize=(3.6 * len(SHAPES_TESTED), 3.6), sharey=True)
    for ax, shape in zip(np.atleast_1d(axes), SHAPES_TESTED):
        for n in POINTS:
            ax.plot(MIXES, [results[shape][n][str(m)] for m in MIXES],
                    "o-", lw=1.4, ms=4, label=f"n={n}")
        ax.set_title(shape, fontsize=10)
        ax.set_xlabel("corner weighting", fontsize=9)
        ax.grid(alpha=0.25, lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    np.atleast_1d(axes)[0].set_ylabel("sampling loss", fontsize=9)
    np.atleast_1d(axes)[0].legend(frameon=False, fontsize=8)
    fig.suptitle("How much of the shape an n-point polygon keeps, "
                 "as anchors move toward the corners", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
