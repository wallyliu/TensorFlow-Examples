"""
Trace emoji silhouettes instead of drawing shapes by hand.

Seventeen hand-drawn shapes have now been rejected on sight by the people who
looked at them, against five that passed, and the redraws have a mixed record
too. The fault is not any one drawing. It is that "draw the picture people
would draw" (BACKLOG 24) has been my hand doing the drawing, and my hand does
not know what people draw.

There is a canonical answer to what people draw, agreed by committee, shipped
on every phone and already installed here: the emoji. Noto Color Emoji is a
BITMAP font, so there are no outlines to extract - but a silhouette can be
traced out of the rendered glyph:

    render at 109 px -> alpha > 128 -> fill holes -> largest component
    -> Moore-neighbour boundary trace -> Douglas-Peucker to a vertex budget

The vertex budget is the knob that sets the price. 44 points is what this run
uses and it is not tuned; a coarser trace costs less distance and loses detail,
which is the same trade as everything else here.

Measured at 44 points, against the hand-drawn version where there is one:

    turtle    9.5 km   mushroom  5.1 km   penguin  18.3 km
    maple    24.5 km  (hand-drawn 13.8)   elephant 25.3 km  (13.5)
    butterfly 28.8 km  (34.3)             giraffe  32.3 km  (13.6)
    crab     51.5 km  (10.7)

The hand-drawn ones are cheaper because they are cruder, and crude is exactly
what got them rejected. What this does not yet answer is whether a traced
outline is RECOGNISED better, which is a rater question like every other one.

Run:  python -m experiments.poc35_emoji_outlines
Out:  results/poc35_emoji.png
"""
import sys
import numpy as np
from PIL import Image, ImageFont, ImageDraw
from scipy import ndimage
from shapely.geometry import Polygon

FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
PX = 109


def mask_of(emoji: str) -> np.ndarray:
    font = ImageFont.truetype(FONT, PX)
    img = Image.new("RGBA", (PX * 3, PX * 3), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((PX, PX), emoji, font=font, embedded_color=True)
    m = np.array(img)[:, :, 3] > 128
    m = ndimage.binary_fill_holes(m)
    lab, n = ndimage.label(m)
    if n == 0:
        raise ValueError("no glyph rendered")
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    return lab == (int(np.argmax(sizes)) + 1)


def trace(mask: np.ndarray) -> np.ndarray:
    """Moore-neighbour boundary following, clockwise, one pixel at a time."""
    pad = np.pad(mask, 1)
    ys, xs = np.nonzero(pad)
    start = (int(ys.min()), int(xs[ys == ys.min()].min()))
    nbrs = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    out, cur, back = [start], start, 6
    while True:
        for k in range(8):
            d = (back + 1 + k) % 8
            ny, nx = cur[0] + nbrs[d][0], cur[1] + nbrs[d][1]
            if pad[ny, nx]:
                back = (d + 4 + 1) % 8
                cur = (ny, nx)
                break
        else:
            break
        if cur == start and len(out) > 2:
            break
        out.append(cur)
        if len(out) > 40000:
            break
    a = np.array(out, dtype=float)
    return np.column_stack([a[:, 1], -a[:, 0]])      # x right, y up


def simplify_to(points: np.ndarray, target: int = 44) -> np.ndarray:
    """Douglas-Peucker, tolerance bisected until the vertex count fits."""
    ring = Polygon(points).buffer(0)
    if ring.geom_type == "MultiPolygon":
        ring = max(ring.geoms, key=lambda g: g.area)
    span = max(points.max(axis=0) - points.min(axis=0))
    lo, hi = 0.0, span / 4
    best = np.array(ring.exterior.coords)[:-1]
    for _ in range(40):
        mid = (lo + hi) / 2
        got = np.array(ring.simplify(mid).exterior.coords)[:-1]
        if len(got) > target:
            lo = mid
        else:
            best, hi = got, mid
    return best


def outline(emoji: str, target: int = 44) -> np.ndarray:
    pts = simplify_to(trace(mask_of(emoji)), target)
    pts = pts - pts.mean(axis=0)
    return pts / max(pts.max(axis=0) - pts.min(axis=0))


if __name__ == "__main__":
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import routeshape.shapes.pack as pack
    import routeshape.describe as describe, routeshape.feasibility as rf
    from routeshape.shapes.library import register
    from routeshape.metrics import thinness
    pack.install()

    WANT = [("🐘", "elephant"), ("🦀", "crab"), ("🦒", "giraffe"),
            ("🍁", "maple"), ("🐧", "penguin"), ("🐢", "turtle"),
            ("🦋", "butterfly"), ("🍄", "mushroom")]
    fig, axes = plt.subplots(2, 4, figsize=(15, 8))
    for ax, (ch, name) in zip(axes.ravel(), WANT):
        try:
            pts = outline(ch)
        except Exception as e:
            ax.set_title(f"{name}: {e}", fontsize=8); ax.axis("off"); continue
        chk = describe.check(pts)
        register("e_" + name, pts)
        km = rf.min_distance_km("e_" + name, "bike", 280)
        c = np.vstack([pts, pts[:1]])
        ax.plot(c[:, 0], c[:, 1], "k-", lw=1.4)
        ok = "" if chk.ok else "  X"
        ax.set_title(f"{name}{ok}  {len(pts)} pts\nfloor {km:.1f} km  "
                     f"thin {thinness(pts):.3f}", fontsize=9)
        ax.set_aspect("equal"); ax.axis("off")
        if not chk.ok:
            print(name, chk.problems)
    plt.tight_layout()
    from routeshape.paths import RESULTS
    p = RESULTS / "poc35_emoji.png"
    plt.savefig(p, dpi=105)
    print(f"wrote {p}")
