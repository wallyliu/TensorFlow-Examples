"""
A wider library of target shapes.

Five shapes was enough to test the pipeline and is not enough to be worth
riding. These are chosen against what the project has measured rather than by
what looks good on a screen:

POC 20 - the identity has to be in the OUTLINE. That is why there is no
Mona Lisa and no portrait: their identity is tone, and an outline of one is an
outline of nobody. Everything here is something you would still know from its
silhouette alone.

POC 29 - the recognition threshold is per shape and nothing predicts it from
geometry, so every shape here starts on the pooled 0.201 and is marked
unmeasured until raters see it. Distinctiveness does NOT buy a higher
threshold: the crescent is the most distinctive shape in the old library and
has nearly the lowest.

route_feasibility - a shape's floor is n_min x street_scale x detour, and
n_min comes from the outline's own detail. Anything needing more distance than
a person will ride is not a shape this product has, however good it looks. The
floors are printed by running this module, and that is the filter.

Coordinates are plain polygons, y up, any scale: shape_library normalises.
"""

from __future__ import annotations

import math

import numpy as np

# Taiwan, from real coastal anchors (lon, lat), longitude squeezed by cos(23.5)
# so the island keeps the proportions it has on a map rather than the ones it
# has in raw degrees.
_TAIWAN_LONLAT = [
    (121.54, 25.30), (122.00, 25.01), (121.87, 24.60), (121.63, 24.00),
    (121.38, 23.10), (121.15, 22.75), (120.90, 22.35), (120.85, 21.90),
    (120.70, 22.20), (120.60, 22.37), (120.45, 22.47), (120.27, 22.60),
    (120.10, 23.05), (120.10, 23.27), (120.13, 23.38), (120.20, 23.75),
    (120.32, 23.93), (120.51, 24.25), (120.67, 24.49), (120.90, 24.85),
    (121.05, 25.03), (121.42, 25.18),
]


def taiwan() -> np.ndarray:
    k = math.cos(math.radians(23.5))
    return np.array([(lon * k, lat) for lon, lat in _TAIWAN_LONLAT])


def fish() -> np.ndarray:
    """Body, tail fin, dorsal and lower fin. No eye - an eye is not an outline."""
    return np.array([
        (0.00, 0.00), (0.18, 0.22), (0.42, 0.30), (0.52, 0.46), (0.62, 0.30),
        (0.86, 0.20), (1.02, 0.06), (1.10, 0.14), (1.06, 0.00), (1.10, -0.14),
        (1.02, -0.06), (0.86, -0.20), (0.62, -0.28), (0.52, -0.44),
        (0.42, -0.26), (0.18, -0.20),
    ])


def butterfly() -> np.ndarray:
    """Two wing pairs meeting at a narrow body, plus antennae."""
    right = [
        (0.03, 0.06), (0.30, 0.44), (0.52, 0.50), (0.56, 0.30), (0.44, 0.14),
        (0.56, 0.04), (0.52, -0.22), (0.36, -0.44), (0.16, -0.40), (0.04, -0.16),
    ]
    pts = [(0.00, 0.62), (0.10, 0.74), (0.06, 0.60)]          # right antenna
    pts += right
    pts += [(0.00, -0.30)]                                     # abdomen tip
    pts += [(-x, y) for x, y in reversed(right)]
    pts += [(-0.06, 0.60), (-0.10, 0.74), (0.00, 0.62)]        # left antenna
    return np.array(pts)


def umbrella() -> np.ndarray:
    """Canopy over a hooked shaft, as ONE closed path.

    Drawn in the order the pen would move: over the dome to the right tip, back
    along the scalloped rim to the centre, down the shaft and round the hook,
    back up the far side of the shaft, then the rest of the rim to the left tip.
    The first attempt drew the dome, the rim and the shaft as three independent
    runs of points and the result crossed itself twice - a closed outline has
    one path and that constraint has to be designed in, not patched after.
    """
    dome = [(0.5 * math.cos(t), 0.42 * math.sin(t))
            for t in np.linspace(math.pi, 0, 26)]
    def scallops(x_from, x_to):
        out = []
        n = 3
        for i in range(n):
            a = x_from + (x_to - x_from) * i / n
            b = x_from + (x_to - x_from) * (i + 1) / n
            out.append(((a + b) / 2, -0.08))
            out.append((b, 0.00))
        return out
    right_rim = scallops(0.50, 0.04)
    left_rim = scallops(-0.04, -0.50)
    shaft = [(0.04, -0.52), (0.02, -0.62), (-0.06, -0.68), (-0.14, -0.62),
             (-0.12, -0.56), (-0.06, -0.60), (-0.02, -0.54), (-0.04, -0.52),
             (-0.04, 0.00)]
    return np.array(dome + right_rim + shaft + left_rim)


def music_note() -> np.ndarray:
    """A quaver as one closed path: round the head, up the stem, out the flag.

    The stem's two edges START and END on the head's rim, at 60 and -10 degrees,
    so the head is traced the long way round between them and nothing crosses.
    Laying a rectangle over a full ellipse instead - the obvious construction -
    puts the stem's near edge inside the head, and the note reads as a cracked
    egg.
    """
    cx, cy, rx, ry = -0.16, -0.34, 0.24, 0.16
    def on_head(deg):
        a = math.radians(deg)
        return (cx + rx * math.cos(a), cy + ry * math.sin(a))
    head = [on_head(d) for d in np.linspace(60, 350, 26)]
    stem_up = [on_head(350), (on_head(350)[0], 0.46)]
    flag = [(0.20, 0.40), (0.31, 0.24), (0.33, 0.04), (0.25, -0.08),
            (0.29, 0.08), (0.25, 0.24), (0.15, 0.34), (on_head(60)[0], 0.40)]
    return np.array(head + stem_up + flag)


def cat() -> np.ndarray:
    """A cat sitting in profile: two ears, a back curve, a tail up the side.

    Replaces a key, which needs its hole to read as a key - and a hole is a
    second contour, which a single closed outline cannot carry. The rule is the
    same one POC 20 found for portraits: if the identity is not in the silhouette
    it does not belong here.
    """
    pts = [
        (-0.16, 0.18), (-0.22, 0.46), (-0.04, 0.34),            # left ear
        (0.10, 0.36), (0.22, 0.48), (0.24, 0.26),               # right ear
        (0.30, 0.14), (0.28, 0.00),                             # cheek, neck
        (0.36, -0.16), (0.40, -0.40), (0.34, -0.54),            # chest, front paw
        (0.10, -0.58), (-0.20, -0.56),                          # base
        # Tail as a TAPERING stroke - the outward edge curls up and the return
        # edge comes back strictly inside it. Drawn as a single wandering line
        # the return crossed the haunch and the cat grew a loop through its own
        # back.
        (-0.34, -0.54), (-0.50, -0.48), (-0.62, -0.30),
        (-0.64, -0.06), (-0.55, 0.10),                          # tail tip
        (-0.50, 0.00), (-0.54, -0.22), (-0.44, -0.38), (-0.32, -0.44),
        (-0.34, -0.20), (-0.30, 0.02),                          # back
    ]
    return np.array(pts)


def lightning() -> np.ndarray:
    return np.array([
        (0.22, 0.50), (-0.28, 0.02), (0.00, 0.02), (-0.22, -0.50),
        (0.30, -0.04), (0.02, -0.04),
    ])


def house() -> np.ndarray:
    return np.array([
        (-0.50, -0.20), (-0.50, 0.14), (-0.34, 0.14), (-0.34, 0.26),
        (0.00, 0.50), (0.50, 0.14), (0.50, -0.20), (0.16, -0.20),
        (0.16, -0.02), (-0.10, -0.02), (-0.10, -0.20),
    ])


def crown() -> np.ndarray:
    return np.array([
        (-0.50, -0.26), (-0.42, 0.20), (-0.24, -0.02), (-0.08, 0.34),
        (0.08, -0.02), (0.26, 0.20), (0.34, -0.26),
    ])


def cup() -> np.ndarray:
    """A mug seen from the side, handle included - the handle is the giveaway."""
    body = [(-0.34, 0.30), (0.20, 0.30), (0.20, 0.14)]
    handle = [(0.30, 0.16), (0.42, 0.06), (0.42, -0.10), (0.30, -0.20),
              (0.22, -0.16), (0.32, -0.08), (0.32, 0.02), (0.22, 0.06)]
    rest = [(0.20, 0.00), (0.14, -0.34), (-0.28, -0.34), (-0.34, 0.00)]
    return np.array(body + handle + rest)


def leaf() -> np.ndarray:
    """A pointed leaf with a stem - two smooth arcs meeting at two cusps."""
    pts = []
    for t in np.linspace(0, 1, 26):
        pts.append((t - 0.5, 0.34 * math.sin(math.pi * t) ** 1.2))
    for t in np.linspace(1, 0, 26):
        pts.append((t - 0.5, -0.34 * math.sin(math.pi * t) ** 1.2))
    pts.append((-0.62, -0.10))
    return np.array(pts)


def plane() -> np.ndarray:
    """From above: fuselage, swept wings, tailplane."""
    right = [(0.05, 0.50), (0.09, 0.22), (0.50, -0.06), (0.50, -0.16),
             (0.09, -0.06), (0.07, -0.34), (0.24, -0.46), (0.24, -0.54),
             (0.04, -0.50)]
    pts = [(0.00, 0.56)] + right + [(0.00, -0.56)]
    pts += [(-x, y) for x, y in reversed(right)]
    return np.array(pts)


PACK = {
    "taiwan": taiwan, "fish": fish, "butterfly": butterfly,
    "umbrella": umbrella, "lightning": lightning, "music_note": music_note,
    "house": house, "crown": crown, "cup": cup, "cat": cat,
    "leaf": leaf, "plane": plane,
}

LABELS = {
    "taiwan": "台灣", "fish": "魚", "butterfly": "蝴蝶", "umbrella": "雨傘",
    "lightning": "閃電", "music_note": "音符", "house": "房子",
    "crown": "皇冠", "cup": "咖啡杯", "cat": "貓", "leaf": "葉子",
    "plane": "飛機",
}


def install() -> list:
    """Register every shape in the pack with shape_library."""
    import shape_library as sl
    for name, fn in PACK.items():
        sl.register(name, fn())
    return list(PACK)


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = install()
    import route_feasibility as rf
    fig, axes = plt.subplots(3, 4, figsize=(11, 9))
    print(f"{'shape':12s}{'n_min':>7}{'min km':>9}{'at 30 km':>10}")
    import shape_library as sl
    for ax, name in zip(axes.ravel(), names):
        xy = sl.resample_by_arclength(name, 600)
        xy = np.vstack([xy, xy[:1]])
        ax.plot(xy[:, 0], xy[:, 1], lw=1.4, color="#2f5d50")
        n, floor = rf.n_min(name), rf.min_distance_km(name)
        p = rf.plan(name, 30.0)
        ax.set_title(f"{name}  n_min {n}  ≥{floor:.1f} km", fontsize=9)
        ax.set_aspect("equal"); ax.axis("off")
        print(f"{name:12s}{n:>7}{floor:>9.1f}"
              f"{(str(p.points) + ' pts') if p.feasible else '  too small':>10}")
    fig.tight_layout()
    fig.savefig("shape_pack.png", dpi=130)
    print("\nwrote shape_pack.png")
