"""
Where along its own outline does a shape keep its identity?

Asked because of a proposal: weight some contour points so the matcher MUST
hit them and let it relax elsewhere. The plumbing is trivial -
`viterbi_closed_loop` already multiplies every emission by one global
`snap_weight`, so a per-point weight is that constant becoming an array. The
question is where the numbers come from.

Two candidates, both computed by flattening one region of the outline at a
time - replacing it with the straight chord across it - and measuring what
that costs:

  SELF          how much shape_distance to the shape's own template rises.
                This is close to curvature, and curvature is not identity: the
                crown is all corners and two raters named it zero times out of
                four.

  DISCRIMINATIVE how much closer the flattened shape moves to its NEAREST
                OTHER shape in the library. This asks what stops it being
                something else, which is the rule the raters gave us in POC 32:
                the shapes people name carry a part nothing else has.

The discriminative map finds them. On the cup it lights the handle root; on the
plane the wingtips; on the gear the CENTRE HOLE, which is exactly what a rater
said was missing before it had one; on the crown the deep valleys rather than
the flat base it shares with every trapezoid.

Run:  python -m experiments.poc34_saliency
Out:  results/poc34_saliency.png
"""
import sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import routeshape.shapes.pack as pack
from routeshape.shapes.library import SHAPES, resample_by_arclength
from routeshape.metrics import shape_distance
from routeshape.paths import RESULTS
pack.install()

N, REGIONS = 256, 32
LIB = ["triangle", "heart", "star5", "crescent", "trex"] + list(pack.LABELS)


def flatten(curve, i, span):
    """Replace one region with the straight chord across it."""
    out = curve.copy()
    idx = [(i * span + k) % len(curve) for k in range(span + 1)]
    a, b = out[idx[0]], out[idx[-1]]
    for k, j in enumerate(idx):
        out[j] = a + (b - a) * (k / (len(idx) - 1))
    return out


def saliency(shape):
    base = resample_by_arclength(shape, N)
    span = N // REGIONS
    others = [resample_by_arclength(o, N) for o in LIB if o != shape]
    near0 = min(shape_distance(base, o) for o in others)
    self_rise, discrim = [], []
    for i in range(REGIONS):
        flat = flatten(base, i, span)
        self_rise.append(shape_distance(flat, base))
        near = min(shape_distance(flat, o) for o in others)
        discrim.append(max(0.0, near0 - near))   # moved TOWARD another shape
    return base, np.array(self_rise), np.array(discrim), span


SHOW = ["cup", "plane", "gear", "crown"]
fig, axes = plt.subplots(2, len(SHOW), figsize=(3.6 * len(SHOW), 7.4))
for col, shape in enumerate(SHOW):
    if shape not in SHAPES:
        import routeshape.shapes.library as sl
        sl.register(shape, pack.RETIRED[shape]())
    base, rise, disc, span = saliency(shape)
    for row, (w, title) in enumerate(((rise, "self"), (disc, "discriminative"))):
        ax = axes[row, col]
        norm = (w - w.min()) / (w.max() - w.min() + 1e-12)
        for i in range(REGIONS):
            idx = [(i * span + k) % N for k in range(span + 1)]
            seg = base[idx]
            ax.plot(seg[:, 0], seg[:, 1], "-", lw=1 + 5 * norm[i],
                    color=plt.cm.YlOrRd(0.25 + 0.75 * norm[i]))
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(f"{shape} · {title}\nmax {w.max():.3f}  min {w.min():.3f}",
                     fontsize=9)
plt.tight_layout()
p = RESULTS / "poc34_saliency.png"
plt.savefig(p, dpi=105)
print(f"wrote {p}")
