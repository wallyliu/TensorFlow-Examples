"""
Exercise the description -> outline loop without the API call.

This sandbox has no Anthropic credentials, so `describe_shape.propose` cannot
run here and the endpoint reports `unavailable`. Everything else in the loop is
testable and is tested here: proposals in exactly the shape the model returns
go through the same checker the live path uses, and the one that passes is
fitted on real streets.

The proposals below are written by hand to stand in for the model's output -
one sound, one that crosses itself the way three of the twelve hand-drawn
shapes did, and one whose detail costs more distance than anyone will ride.
Both negative cases had to be rebuilt: the first "broken" boat did not actually
cross (its mast was an out-and-back, which is legal) and the first
over-detailed shape was rejected for crossing instead of for cost, so neither
tested the rule it was aimed at.
What that establishes is that the checker catches the failures and the
survivor draws; what it does NOT establish is that the model returns good
proposals, or how often it needs a second attempt. Those need a key.

Run:  python poc31_describe_loop.py
Out:  poc31_describe_loop.png
"""

from __future__ import annotations

import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import routeshape.describe as ds
import routeshape.feasibility as rf
import routeshape.shapes.pack as shape_pack
import routeshape.street_scale as ss
from poc30_pack_fits import LAT, LON, MODE, fit_one
from routeshape.shapes.library import register, resample_by_arclength

# A rabbit: two ears, a round body, a scut. Identity is entirely silhouette.
RABBIT = [
    (-0.10, 0.10), (-0.17, 0.44), (-0.12, 0.62), (-0.04, 0.60), (-0.02, 0.40),
    (0.03, 0.16), (0.08, 0.40), (0.12, 0.62), (0.20, 0.64), (0.22, 0.44),
    (0.17, 0.10), (0.26, -0.02), (0.30, -0.20), (0.26, -0.38), (0.12, -0.46),
    (-0.14, -0.46), (-0.30, -0.36), (-0.40, -0.40), (-0.46, -0.30),
    (-0.38, -0.24), (-0.30, -0.28), (-0.26, -0.16), (-0.22, -0.02),
]
# A sailboat whose sail genuinely crosses its own mast. The FIRST attempt at a
# negative case here did not cross at all - its mast was drawn out and back,
# which is legal - so the checker passed it and the test proved nothing. An
# example has to be built to fail the specific rule it is aimed at.
BAD_BOAT = [
    (-0.45, -0.20), (0.45, -0.20), (0.32, -0.40), (-0.32, -0.40),
    (0.00, 0.50), (0.30, 0.05), (-0.30, 0.05),
]
# A gear: no crossings anywhere, just sixteen teeth. Aimed at the distance rule,
# not the geometry one. The first attempt was a snowflake whose arms crossed, so
# it was rejected for the wrong reason and said nothing about cost.
def gear(teeth: int = 16):
    pts = []
    for k in range(teeth):
        a0 = 2 * math.pi * k / teeth
        a1 = 2 * math.pi * (k + 0.5) / teeth
        a2 = 2 * math.pi * (k + 1) / teeth
        pts.append((0.34 * math.cos(a0), 0.34 * math.sin(a0)))
        pts.append((0.50 * math.cos(a0), 0.50 * math.sin(a0)))
        pts.append((0.50 * math.cos(a1), 0.50 * math.sin(a1)))
        pts.append((0.34 * math.cos(a2), 0.34 * math.sin(a2)))
    return pts

PROPOSALS = [("一隻兔子", "rabbit", RABBIT),
             ("一艘帆船", "sailboat", BAD_BOAT),
             ("一個齒輪", "gear", gear())]


def main() -> None:
    shape_pack.install()
    scale = ss.scale_for(LAT, LON, MODE, rf.MODES[MODE]["street_scale_m"])
    results = []
    for description, name, pts in PROPOSALS:
        verdict = ds.check(pts, MODE, scale)
        print(f"\n{description} ({name}): {'PASSES' if verdict.ok else 'REJECTED'}")
        print(f"  {verdict.metrics}")
        for problem in verdict.problems:
            print(f"  - {problem[:150]}")
        results.append((description, name, pts, verdict))

    good = [r for r in results if r[3].ok]
    fits = {}
    for description, name, pts, verdict in good:
        register(name, np.asarray(pts, float))
        target = round(max(10.0, verdict.metrics["min_km"] * 1.6))
        print(f"\nfitting {name} at {target} km...", flush=True)
        fit = fit_one(name, target, scale)
        fits[name] = fit
        if fit.get("status") == "ok":
            print(f"  {fit['route_km']:.1f} km, shape distance {fit['distance']:.3f}")
        else:
            print(f"  {fit.get('status')}")

    cols = len(results)
    fig, axes = plt.subplots(2, cols, figsize=(3.2 * cols, 6.2))
    for col, (description, name, pts, verdict) in enumerate(results):
        closed = np.vstack([np.asarray(pts, float), np.asarray(pts, float)[:1]])
        colour = "#2f5d50" if verdict.ok else "#9a3b1f"
        axes[0][col].plot(closed[:, 0], closed[:, 1], lw=1.3, color=colour)
        head = "accepted" if verdict.ok else "rejected"
        axes[0][col].set_title(f"{name}\n{head}", fontsize=10, color=colour)
        fit = fits.get(name)
        if fit and fit.get("status") == "ok":
            xy = fit["xy"]
            axes[1][col].plot(xy[:, 0], xy[:, 1], lw=1.0, color="#c0392b")
            axes[1][col].set_title(f"{fit['route_km']:.0f} km · "
                                   f"{fit['distance']:.3f}", fontsize=9)
        else:
            axes[1][col].text(0.5, 0.5, verdict.problems[0][:60] + "…",
                              ha="center", va="center", fontsize=7,
                              color="#9a3b1f", wrap=True,
                              transform=axes[1][col].transAxes)
    for ax in axes.ravel():
        ax.set_aspect("equal"); ax.axis("off")
    fig.tight_layout(); fig.savefig("poc31_describe_loop.png", dpi=140)
    print("\nwrote poc31_describe_loop.png")


if __name__ == "__main__":
    main()
