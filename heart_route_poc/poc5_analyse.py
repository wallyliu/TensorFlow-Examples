"""
POC 5, step 6 - score every metric variant against the human data.

Two labelling runs produced two kinds of evidence:

  DIRECTIONAL  8 judgements where the rater picked one shape as more
               heart-like. A metric must order those the same way.
  TILT         8 pairs showing the SAME route with one copy rotated 20 or 40
               degrees, all answered "about the same". A metric must therefore
               score a rotated copy about the same as its original.

The second is the one that matters, because it tests a premise this project
asserted three times without ever checking it. POC 3 treated the metric's
blindness to tilt as the bug; POC 4 built rotation sensitivity in as the fix and
called the classic rotation-INVARIANT formulation "the exact property that
needed avoiding". The rater says tilt does not reduce heart-likeness at all - so
the blindness was correct behaviour, and the fix introduced the error.

Run:  python poc5_analyse.py
Out:  poc5_metric_verdict.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from heart_route_poc import generate_heart_points
from heart_route_poc3 import HEART_WIDTH_M
from shape_metrics import (
    chamfer_upright, procrustes_upright, procrustes_upright_fft, turning_upright,
)

POOL = Path(__file__).with_name("poc5_pool.npz")
OUT_PNG = Path(__file__).with_name("poc5_metric_verdict.png")

# Every judgement where the rater actually chose, across both runs, as
# (more heart-like, less heart-like).
DIRECTIONAL = [
    ("real07", "cleft_filled"), ("real10", "cleft_filled"), ("real02", "cleft_filled"),
    ("real03", "cleft_filled"), ("flank_changed", "cleft_filled"),
    ("real02", "cleft_filled"), ("real07", "cleft_filled"), ("real10", "cleft_filled"),
]
TILT_SOURCES = ["real07", "real02", "real10", "real11"]
TILT_ANGLES = [20, 40]
TIE_BAND = 1.5  # a metric may charge up to this ratio and still count as "about the same"


def rotate(xy: np.ndarray, degrees: float) -> np.ndarray:
    theta = np.radians(degrees)
    r = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    centre = xy.mean(axis=0)
    return (xy - centre) @ r.T + centre


def main() -> None:
    pool = np.load(POOL, allow_pickle=True)
    template = generate_heart_points(2048) * HEART_WIDTH_M

    variants = {
        "chamfer\n(upright)": lambda a: chamfer_upright(a, template),
        "procrustes\nrotation-sensitive": lambda a: procrustes_upright_fft(a, template),
        "procrustes\nrotation-invariant": lambda a: procrustes_upright(a, template, allow_rotation=True),
        "turning\nrotation-sensitive": lambda a: turning_upright(a, template),
        "turning\nrotation-invariant": lambda a: turning_upright(a, template, rotation_invariant=True),
    }

    direction, tilt = {}, {}
    for name, fn in variants.items():
        direction[name] = sum(
            1 for better, worse in DIRECTIONAL
            if fn(pool[f"{better}__xy"]) < fn(pool[f"{worse}__xy"])
        )
        ratios = []
        for source in TILT_SOURCES:
            base = pool[f"{source}__xy"]
            reference = fn(base)
            ratios += [fn(rotate(base, angle)) / reference for angle in TILT_ANGLES]
        tilt[name] = float(np.mean(ratios))

    print(f"{'variant':<34}{'directional':>13}{'tilt ratio':>13}{'verdict':>26}")
    print("-" * 86)
    for name in variants:
        flat = name.replace("\n", " ")
        passes = direction[name] == len(DIRECTIONAL) and tilt[name] <= TIE_BAND
        verdict = ("agrees with the human" if passes else
                   "fails tilt" if direction[name] == len(DIRECTIONAL) else
                   "fails direction" if tilt[name] <= TIE_BAND else "fails both")
        print(f"{flat:<34}{direction[name]}/{len(DIRECTIONAL):<11}{tilt[name]:>12.2f}x{verdict:>26}")

    names = list(variants)
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.6))
    colors = ["#1a7f37" if (direction[n] == len(DIRECTIONAL) and tilt[n] <= TIE_BAND)
              else "#c94a3f" for n in names]

    axes[0].bar(range(len(names)), [direction[n] for n in names], color=colors)
    axes[0].axhline(len(DIRECTIONAL), color="#666", ls=":", lw=1)
    axes[0].set_ylim(0, len(DIRECTIONAL) + 0.6)
    axes[0].set_ylabel("judgements ordered correctly")
    axes[0].set_title("Directional agreement\n8 pairs the rater actually chose between", fontsize=11)

    axes[1].bar(range(len(names)), [tilt[n] for n in names], color=colors)
    axes[1].axhline(1.0, color="#666", ls="-", lw=1)
    axes[1].axhspan(0, TIE_BAND, color="#1a7f37", alpha=0.08)
    axes[1].set_ylabel("score of rotated copy ÷ score of original")
    axes[1].set_title("Tilt\nrater called all 8 rotated pairs \"about the same\"\n"
                      "(green band = metric agrees)", fontsize=11)

    for ax in axes:
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontsize=9)
    fig.suptitle("POC 5 — the only variant that matches the human on both is the one "
                 "POC 4 argued against", fontsize=13)
    fig.savefig(OUT_PNG, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nsaved {OUT_PNG}")


if __name__ == "__main__":
    main()
