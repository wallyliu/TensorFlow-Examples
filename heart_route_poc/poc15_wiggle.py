"""
A wander term for the metric, and an honest account of what it rests on.

POC 14 settled that equal shape distance is not equal damage, and in the
direction opposite to the one the test was built to catch: three raters
preferred the dinosaur with its leg gap erased over noise of identical shape
distance, eight of eight decided judgements, p = 0.008. Losing one clean feature
costs less than the same error spread out as wander.

`shape_distance` cannot see that, and the reason is structural. It resamples
both curves to n points and matches positions; a curve that wanders back and
forth across the template still puts its points near the template, so the
distance stays low while the curve itself gets much longer. Length is exactly
what it throws away.

    wander = arclength(route) / arclength(template) - 1,  floored at 0
    distance_v2 = shape_distance + WANDER_WEIGHT * wander

WANDER_WEIGHT is fitted to four rungs of one shape. That is not a validated
constant and this file does not pretend otherwise: `main` reports the fit, then
checks the one thing that can be checked without more raters - whether the
term behaves the same way on shapes it was not fitted to.

The rater round happened. POC 18: the DIRECTION replicates on three unseen
shapes - eight of eight decided judgements prefer the member with a feature
destroyed, p = 0.008 - and the CALIBRATION does not, 3 of 12 predictions right.
Worse than the number being wrong, no number works: a "merged" answer puts a
lower bound on the weight and a "tie" puts an upper bound, and the answers need
w > 4.1 and w < 2.6 at once. The weighted-sum FORM is what fails, not 0.7.

So the term below is kept for what it measures and not for what it predicts.
See poc18_heldout.py.

Run:  python poc15_wiggle.py
Out:  poc15_wiggle.png, poc15_wiggle.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from heart_route_poc4 import smooth_noise
from poc13_dino_stimuli import ALPHAS, deepest_fjord, fill_span, match_noise
from shape_library import resample_by_arclength
from shape_metrics import shape_distance

N = 512
SCALE_M = 2000.0
# Which feature each shape's ladder destroys. The dinosaur keeps the leg gap
# so its rungs stay identical to the ones the raters actually saw. The others
# use their largest outward feature instead: closing their deepest notch is too
# small a change to reach the distance range where the dinosaur effect lived
# (heart tops out at 0.061, crescent at 0.027), and a ladder that never enters
# the interesting range cannot test anything.
FEATURE = {"trex": "fjord", "heart": "spike", "star5": "spike",
           "crescent": "spike"}
SHAPES = ["trex", "heart", "star5", "crescent"]
FITTED_ON = "trex"

# The threshold POC 6 measured for "a person reliably sees a difference".
DISCRIMINATION = 0.10
WANDER_WEIGHT = 0.7

OUT_PNG = Path(__file__).with_name("poc15_wiggle.png")
OUT_JSON = Path(__file__).with_name("poc15_wiggle.json")

# What the raters said, rung by rung, for the shape the weight was fitted on.
DINO_HUMAN = {"L1": "tie x3", "L2": "tie, merged, merged",
              "L3": "merged x3", "L4": "merged x3"}


def arclength(xy: np.ndarray) -> float:
    closed = np.vstack([xy, xy[:1]])
    return float(np.hypot(*np.diff(closed, axis=0).T).sum())


def wander(xy: np.ndarray, template: np.ndarray) -> float:
    """How much longer the curve is than the shape it is drawing."""
    return max(0.0, arclength(xy) / arclength(template) - 1.0)


def distance_v2(xy: np.ndarray, template: np.ndarray,
                weight: float = WANDER_WEIGHT) -> float:
    """Shape distance, plus a penalty for getting there the long way round."""
    return shape_distance(xy, template) + weight * wander(xy, template)


def biggest_spike(xy: np.ndarray, max_span: float = 0.18
                  ) -> tuple[list[int], float]:
    """
    The span that stands furthest out from its own chord.

    `deepest_fjord` finds a notch cut INTO the shape - the dinosaur's leg gap,
    a heart's cleft. This finds the opposite: a point of a star, a lobe of a
    heart, the horn of a crescent. Same idea, measured as height above the
    chord rather than arc length along it.
    """
    n = len(xy)
    best, best_height = None, 0.0
    for span in range(int(0.06 * n), int(max_span * n), max(1, n // 128)):
        for i in range(0, n, max(1, n // 256)):
            indices = [(i + k) % n for k in range(span + 1)]
            seg = xy[indices]
            d = seg[-1] - seg[0]
            length = float(np.hypot(*d))
            if length <= 0:
                continue
            unit = d / length
            height = float(np.abs(unit[0] * (seg[:, 1] - seg[0, 1])
                                  - unit[1] * (seg[:, 0] - seg[0, 0])).max())
            if height > best_height:
                best_height, best = height, indices
    return best, best_height


def ladder(shape: str) -> list[dict]:
    """The same iso-distance ladder POC 13 built, for any shape."""
    clean = resample_by_arclength(shape, N) * SCALE_M
    if FEATURE[shape] == "fjord":
        indices, ratio = deepest_fjord(clean)
    else:
        indices, ratio = biggest_spike(clean)
    rungs = []
    for k, alpha in enumerate(ALPHAS, start=1):
        merged, _ = fill_span(clean, indices, alpha)
        d = shape_distance(merged, clean)
        noisy, amp = match_noise(clean, d, seed=1)
        rungs.append({
            "rung": f"L{k}", "alpha": alpha, "shape_distance": d,
            "noise_amplitude_m": amp,
            "wander_merged": wander(merged, clean),
            "wander_noise": wander(noisy, clean),
            "v2_merged": distance_v2(merged, clean),
            "v2_noise": distance_v2(noisy, clean),
            "feature_size": ratio,
            "feature_kind": FEATURE[shape],
        })
    return rungs


def main() -> None:
    results = {"wander_weight": WANDER_WEIGHT, "fitted_on": FITTED_ON,
               "discrimination_threshold": DISCRIMINATION, "shapes": {}}

    for shape in SHAPES:
        rungs = ladder(shape)
        results["shapes"][shape] = rungs
        tag = "  (weight fitted here)" if shape == FITTED_ON else ""
        print(f"\n=== {shape}{tag}")
        print(f"  {'rung':<5}{'distance':>9}{'wander merged':>15}{'wander noise':>14}"
              f"{'v2 gap':>9}{'predicts':>11}")
        for r in rungs:
            gap = r["v2_noise"] - r["v2_merged"]
            predicts = "merged" if gap > DISCRIMINATION else "tie"
            r["v2_gap"] = gap
            r["predicts"] = predicts
            line = (f"  {r['rung']:<5}{r['shape_distance']:9.3f}"
                    f"{r['wander_merged']:15.3f}{r['wander_noise']:14.3f}"
                    f"{gap:9.3f}{predicts:>11}")
            if shape == FITTED_ON:
                line += f"    human: {DINO_HUMAN[r['rung']]}"
            print(line)

        # The check that does not need raters: does the term point the same way
        # on a shape it was not fitted to?
        ordered = all(r["wander_noise"] > r["wander_merged"] for r in rungs)
        monotone = all(b["v2_gap"] > a["v2_gap"]
                       for a, b in zip(rungs, rungs[1:]))
        print(f"  wander always higher for noise: {ordered};  gap monotone: {monotone}")
        results["shapes"][shape] = {"rungs": rungs, "noise_wanders_more": ordered,
                                    "gap_monotone": monotone}

    fig, axes = plt.subplots(1, len(SHAPES), figsize=(4.0 * len(SHAPES), 3.8),
                             sharey=True)
    for ax, shape in zip(np.atleast_1d(axes), SHAPES):
        rungs = results["shapes"][shape]["rungs"]
        xs = [r["shape_distance"] for r in rungs]
        ax.plot(xs, [r["v2_merged"] for r in rungs], "o-", color="#2f5d50",
                lw=1.8, ms=6, label="feature destroyed")
        ax.plot(xs, [r["v2_noise"] for r in rungs], "o-", color="#b4622c",
                lw=1.8, ms=6, label="matched wander")
        ax.plot(xs, xs, "--", color="#9aa09c", lw=1.2, label="shape distance alone")
        ax.set_title(shape + ("  (fitted here)" if shape == FITTED_ON else ""),
                     fontsize=10)
        ax.set_xlabel("shape distance\n(identical for both)", fontsize=9)
        ax.grid(alpha=0.25, lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    np.atleast_1d(axes)[0].set_ylabel("distance_v2", fontsize=9)
    np.atleast_1d(axes)[0].legend(frameon=False, fontsize=8)
    fig.suptitle("shape_distance calls every pair identical (dashed). "
                 "The wander term separates them the way the raters did.",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
