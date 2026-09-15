"""
Taipei 101 as a closed contour.

Chosen over the Mona Lisa for the reason POC 20 measured: this pipeline can
draw shapes whose identity lives in their OUTLINE, and a stepped tower is the
purest case of that. Nobody recognises 101 by its shading; they recognise the
eight flared modules and the spire, and every one of those is a silhouette
feature.

Built from proportions rather than traced, so it is reproducible and the
parameters say what they mean. The real building is 508 m to the tip of the
spire and 448 m to the roof, with eight eight-floor modules above a tapered
base; the numbers below are those ratios.
"""

from __future__ import annotations

import numpy as np

MODULES = 8
PODIUM_HALF = 0.50         # the skirt at the bottom, widest part of the outline
PODIUM_TOP = 0.085
BASE_BOTTOM_HALF = 0.235   # the tapered section between podium and the modules
BASE_TOP_HALF = 0.150
BASE_TOP = 0.265
MODULE_BOTTOM_HALF = 0.150
MODULE_TOP_HALF = 0.196    # each module flares OUTWARD going up - the signature
MODULES_TOP = 0.862
CROWN_HALF = 0.070
CROWN_TOP = 0.905
SPIRE_HALF = 0.012
SPIRE_TOP = 1.0


def half_profile() -> list[tuple[float, float]]:
    """The right-hand edge, bottom to top. Mirrored to close the outline."""
    pts = [(PODIUM_HALF, 0.0), (PODIUM_HALF, PODIUM_TOP),
           (BASE_BOTTOM_HALF, PODIUM_TOP), (BASE_TOP_HALF, BASE_TOP)]
    height = (MODULES_TOP - BASE_TOP) / MODULES
    for i in range(MODULES):
        bottom = BASE_TOP + i * height
        pts.append((MODULE_BOTTOM_HALF, bottom))
        pts.append((MODULE_TOP_HALF, bottom + height))
    pts.append((CROWN_HALF, CROWN_TOP))
    pts.append((SPIRE_HALF, SPIRE_TOP))
    return pts


def outline() -> np.ndarray:
    """The full closed outline, centred, with height normalised to 1."""
    right = half_profile()
    left = [(-x, y) for x, y in reversed(right)]
    pts = np.array(right + left, dtype=float)
    pts[:, 1] -= pts[:, 1].mean()
    return pts


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    o = outline()
    closed = np.vstack([o, o[:1]])
    fig, ax = plt.subplots(figsize=(4, 7))
    ax.plot(closed[:, 0], closed[:, 1], lw=1.6, color="#1a1a1a")
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig("taipei101.png", dpi=140)
    print(f"{len(o)} vertices")
