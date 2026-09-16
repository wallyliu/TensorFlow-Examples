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

DRAW THE CONVENTION, NOT THE OBJECT. Seven of the fourteen here were rejected
on sight by the first person to look at them, and not one was rejected for
being geometrically wrong. The cat was a correct cat and everybody read
Pikachu, because tall pointed ears on a round body with no neck is somebody
else's silhouette. The crown was a correct heraldic crown and everybody read a
mountain range, because a zigzag on a trapezoid IS a mountain range - what
makes a crown is vertical sides, a band, and balls on the points. The gear had
sixteen correct involute-ish teeth and read as a sun. The reader is matching
against the picture they would draw, so that is the target: a butterfly drawn
the way it is drawn here, not the way one photographs.

Which also means the convention is LOCAL. The first butterfly was rejected with
"跟台灣的習慣畫法差很多" - the shape was fine, the convention was the wrong
one. Anything added here should be checked against the people who will ride it.

THE VALIDATOR CANNOT DO THIS JOB. Every shape in this file passed
describe.check() before any of the above was noticed. It validates a polygon -
no self-crossings, a sane aspect ratio, a floor a person will ride - and there
is no mechanical test for whether a drawing looks like its name. A person
looking at it is not a nice-to-have step here, it is the only step that works.

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


def _sym(right: list, top: tuple, bottom: tuple) -> np.ndarray:
    """A left-right symmetric outline from its right half.

    Hand-mirroring is how three of these shapes grew self-crossings: the
    reversed half was pasted in the wrong direction and the boundary tied a
    knot. Building both halves from one list cannot do that.
    """
    return np.array([top] + right + [bottom]
                    + [(-x, y) for x, y in reversed(right)])


def taiwan() -> np.ndarray:
    k = math.cos(math.radians(23.5))
    return np.array([(lon * k, lat) for lon, lat in _TAIWAN_LONLAT])


def fish() -> np.ndarray:
    """A deep body, a tall dorsal fin and a caudal fin a quarter of the length.

    The first version was a diamond with a small forked spur for a tail and
    read as a leaf with a thorn. The tail is what says fish, so it is drawn at
    the size a fish's tail actually occupies rather than at the size that fits
    neatly beside the body.
    """
    return np.array([
        (0.50, 0.00), (0.40, 0.18), (0.22, 0.28), (0.04, 0.30),
        (-0.10, 0.48), (-0.20, 0.26),                   # dorsal fin
        (-0.30, 0.14),                                  # peduncle, top
        (-0.56, 0.34), (-0.42, 0.00), (-0.56, -0.30),   # caudal fin
        (-0.30, -0.12),                                 # peduncle, bottom
        (-0.14, -0.24),
        (0.00, -0.28), (0.06, -0.46), (0.18, -0.28),    # pelvic fin
        (0.34, -0.20), (0.44, -0.10),
    ])


def butterfly() -> np.ndarray:
    """A swallowtail: upper wings swept up and out, lower wings with tails.

    Two earlier versions were rejected by eye and each taught something. The
    first carried hair-thin antennae, 3% of the width, which no street network
    can draw - they cost distance and rendered as nothing. The second dropped
    them but left the notch between the upper wings shallow, and the two wings
    fused into what everybody read as a heart.

    This one is the shape a person here would draw if asked for a butterfly,
    which is not the same shape as a photograph of one. That difference is the
    point: the target has to match the reader's convention, not the object.
    """
    return _sym([
        (0.10, 0.40), (0.30, 0.62), (0.50, 0.52), (0.44, 0.24), (0.22, 0.08),
        (0.10, 0.02),                                   # waist
        (0.28, -0.10), (0.40, -0.26), (0.30, -0.40), (0.34, -0.56),
        (0.16, -0.40), (0.08, -0.32),                   # lower wing + tail
    ], (0.00, 0.20), (0.00, -0.42))


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
    x_r = on_head(350)[0]
    x_l = on_head(60)[0]
    # The flag leaves and rejoins the RIGHT edge below the stem's top, then the
    # stem continues up and caps across to the left edge. Returning from the
    # flag straight to the left edge instead draws a line from x=+0.17 to
    # x=-0.04 that passes through the stem at x=+0.076 - a real crossing,
    # invisible at render size and found only by the checker.
    stem_a = [on_head(350), (x_r, 0.20)]
    # The flag's two edges must not cross EACH OTHER either: the first rewrite
    # fixed the flag-through-stem crossing and left the outward and return
    # edges meeting near the base. Outward runs along the flag's lower edge to
    # the tip, the return along its upper edge, and the return rejoins the stem
    # ABOVE where the outward left it, so the two never share a y range.
    flag = [(0.22, 0.16), (0.33, 0.04), (0.30, -0.10),          # lower edge, tip
            (0.36, 0.02), (0.34, 0.20), (0.24, 0.30), (x_r, 0.30)]   # upper edge
    top = [(x_r, 0.50), (x_l, 0.50)]
    return np.array(head + stem_a + flag + top)





def cat() -> np.ndarray:
    """A cat facing front: a big head with two ears, a small body, a thick tail.

    Three versions were rejected before this one and each named its own fault.
    The first was read by everyone as Pikachu - tall pointed ears on a round
    body with no neck is somebody else's silhouette. The second was a sitting
    profile, correct in every part and unrecognisable, because a cat seen side
    on is a shape any four-legged animal makes.

    What fixed it was moving the budget. Half the contour of a sitting cat is
    spent on a body, a foreleg and a haunch that carry no identity at all; a
    cat is its head, and the head is two triangles. So the head is drawn at
    cartoon proportion - 0.80 wide against a 0.60 body - and the rest is there
    to say cat rather than cat's head.

    THE TAIL IS THE WEAK PART and it is worth knowing why before redrawing it
    again. A tail is a stroke, and a closed outline can only draw a stroke as a
    long thin loop: too thin and the streets cannot render it, thick enough to
    render and it reads as a leg. Three attempts all came out as a hook hanging
    off the side. This one is the thickest of them - `metrics.thinness` 0.066,
    which is below the warning line - and it survives at 30 km because the loop
    is 14% of the width, not because the problem is solved.
    """
    return np.array([
        (0.00, 0.28),
        (-0.11, 0.32), (-0.21, 0.55), (-0.32, 0.29),          # left ear
        (-0.40, 0.12), (-0.40, -0.04), (-0.32, -0.14),        # head, jaw
        (-0.28, -0.24), (-0.30, -0.40), (-0.24, -0.50),       # body, foot
        (-0.04, -0.54), (0.16, -0.52), (0.26, -0.46),         # base
        (0.42, -0.52), (0.58, -0.48), (0.70, -0.34),          # tail, outer
        (0.68, -0.16), (0.56, -0.06),                         # tail tip
        (0.52, -0.16), (0.54, -0.32), (0.46, -0.40),          # tail, inner
        (0.34, -0.40), (0.28, -0.28),
        (0.28, -0.16), (0.32, -0.14),                         # body right, jaw
        (0.40, -0.04), (0.40, 0.12),                          # head right
        (0.32, 0.29), (0.21, 0.55), (0.11, 0.32),             # right ear
    ])


def cat_head() -> np.ndarray:
    """The same head with nothing else: the cheapest shape in the pack.

    Kept as its own shape rather than as a replacement for `cat`, because the
    two are different rides and nobody yet knows which is more recognisable -
    that is a question for raters, not for whoever drew them.

    What it costs and what it buys, measured in Taipei: a floor of 7.8 km
    against the cat's 10.6, `n_min` 24, and `metrics.thinness` 0.390 - the
    highest in the pack, because there is nothing thin in it anywhere. It
    fitted at 0.036 over 24.4 km, the closest fit this project has produced
    for any shape, and still reads as a cat's head at 10 km (0.117).

    A version with eyes and a nose was built and dropped. `multi_contour` can
    carry them - they route, and at 40 km they came out legible - but n_min
    goes 24 -> 92 and the floor 7.8 km -> 34.3, and the connectors the merge
    needs cross the cheek as visible lines. Four times the ride for a face
    with a scar through it.
    """
    return _sym([
        (0.12, 0.34), (0.22, 0.58), (0.34, 0.30),      # ear
        (0.42, 0.14), (0.44, -0.06),
        (0.36, -0.26), (0.22, -0.40), (0.10, -0.46),   # cheek, jaw
    ], (0.00, 0.28), (0.00, -0.48))


def lightning() -> np.ndarray:
    return np.array([
        (0.22, 0.50), (-0.28, 0.02), (0.00, 0.02), (-0.22, -0.50),
        (0.30, -0.04), (0.02, -0.04),
    ])


def house() -> np.ndarray:
    """Overhanging eaves, a chimney and a door.

    The plain pentagon it replaces was not wrong, it was generic - a house
    shares its outline with a great many things until it has the parts people
    draw on a house.
    """
    return np.array([
        (-0.46, -0.36), (-0.10, -0.36), (-0.10, -0.06),
        (0.12, -0.06), (0.12, -0.36), (0.46, -0.36),    # door
        (0.46, 0.06), (0.56, 0.10),                     # eave
        (0.00, 0.46),                                   # ridge
        (-0.26, 0.28), (-0.26, 0.48), (-0.40, 0.48), (-0.40, 0.18),
        (-0.56, 0.10), (-0.46, 0.06),                   # chimney, eave
    ])


def crown() -> np.ndarray:
    """A banded crown with a ball on each of three points.

    The version this replaces was a zigzag on a trapezoid and every reader
    called it a mountain range, correctly: mountains are exactly a zigzag on a
    trapezoid. Two things separate a crown from a skyline and neither is the
    zigzag - the sides are VERTICAL and there is a band across the bottom. The
    balls are the third, and they are what a person here pictures first.
    """
    return _sym([
        (0.09, 0.44), (0.12, 0.36), (0.08, 0.28),          # centre ball
        (0.06, 0.18), (0.16, -0.08),                       # stem, valley
        (0.25, 0.14), (0.27, 0.23),                        # side point
        (0.20, 0.30), (0.24, 0.40), (0.34, 0.41),
        (0.39, 0.33), (0.35, 0.23),                        # side ball
        (0.34, 0.08), (0.36, -0.14),                       # outer edge
        (0.48, -0.18), (0.48, -0.44),                      # band, base
    ], (0.00, 0.48), (0.00, -0.44))


def cup() -> np.ndarray:
    """A mug seen from the side, handle included - the handle is the giveaway."""
    body = [(-0.34, 0.30), (0.20, 0.30), (0.20, 0.14)]
    handle = [(0.30, 0.16), (0.42, 0.06), (0.42, -0.10), (0.30, -0.20),
              (0.22, -0.16), (0.32, -0.08), (0.32, 0.02), (0.22, 0.06)]
    rest = [(0.20, 0.00), (0.14, -0.34), (-0.28, -0.34), (-0.34, 0.00)]
    return np.array(body + handle + rest)


def leaf(veins: int = 0) -> np.ndarray:
    """A leaf WITH its midrib and side veins, as one closed route.

    Without veins this was just a pointed ellipse and read as an eye or a
    lens - the first version was rejected on exactly that. A leaf's identity is
    the venation, not the silhouette, which is the one case where POC 20's rule
    points inward: the inside marks ARE the outline here, not shading.

    A closed route can draw an interior line by going out along it and back,
    which costs twice its length and nothing else - the same out-and-back
    `multi_contour.merge` uses for its connectors. So the path runs the whole
    blade, then walks the midrib tip to tip, branching off to each vein root
    and returning, and comes back to where it started.

    The price is steep and it is the reason `leaf` ships with the midrib alone:

        midrib only   n_min  56   >= 21 km
        1 pair        n_min 136   >= 61 km
        2 pairs       n_min 188   >= 90 km

    The midrib by itself is already enough to stop it reading as an eye, for a
    distance somebody will actually ride. The full venation was built, fitted
    and dropped: a 2-pair leaf asked for at 100 km came back 79.7 km at a shape
    distance of 0.250, with the side veins landing as blobs - past the pooled
    recognition threshold, so the street network cannot draw them and shipping
    it would only sell a 90 km ride that does not work.

    Note the 2-pairs-but-shorter variant costs MORE, not less - n_min 208
    against 188, 107 km against 90 - because a shorter vein is a FINER feature,
    and n_min tracks the finest feature rather than the total amount of ink.
    """
    def edge(t, sign):
        return (t - 0.5, sign * 0.34 * math.sin(math.pi * t) ** 1.2)

    blade = [edge(t, 1) for t in np.linspace(0, 1, 26)]
    blade += [edge(t, -1) for t in np.linspace(1, 0, 26)]
    stem = [(-0.62, -0.10), (-0.5, 0.0)]

    # Midrib left tip to right tip, dropping a vein each side on the way.
    path = list(blade) + stem
    for i in range(veins + 1 if veins else 0):
        t = 0.12 + 0.72 * i / veins
        base = (t - 0.5, 0.0)
        path.append(base)
        if i == veins:
            break
        for sign in (1, -1):
            # Out to the blade and back: a vein reaching about two thirds of
            # the way to the edge, angled forward the way a real one runs.
            tip_t = min(0.97, t + 0.13)
            ex, ey = edge(tip_t, sign)
            path.append((base[0] + (ex - base[0]) * 0.72,
                         base[1] + (ey - base[1]) * 0.72))
            path.append(base)
    path.append((0.47, 0.0))          # midrib reaches the tip
    path += [(t - 0.5, 0.0) for t in np.linspace(0.97, 0.0, 8)]   # and back
    return np.array(path)


def rabbit() -> np.ndarray:
    """Face on: two long ears, a round head, a body and two feet.

    Drawn in profile it was unreadable - not wrong in any part, just not
    recognisable, which is the only test that counts. Face on it is symmetric,
    and a symmetric animal is far easier to name than a silhouette of the same
    animal side on.
    """
    return _sym([
        (0.07, 0.40), (0.13, 0.62), (0.21, 0.74), (0.28, 0.66),  # ear
        (0.26, 0.42), (0.20, 0.28),
        (0.27, 0.16), (0.27, 0.02),                              # cheek
        (0.19, -0.06),                                           # neck
        (0.33, -0.16), (0.37, -0.34),                            # body
        (0.31, -0.46), (0.17, -0.50), (0.11, -0.40),             # foot
    ], (0.00, 0.26), (0.00, -0.34))


def gear(teeth: int = 8) -> np.ndarray:
    """Eight square teeth with flat tops and flat valleys.

    Sixteen pointed teeth over a V-shaped valley is the outline of a sun, not
    of a gear, and at any distance a person will ride the teeth came out as
    noise indistinguishable from the street grid. Halving the count and
    squaring the profile doubles the width of every tooth and costs nothing
    that reads: the floor drops from 22.0 km to 10.5 km.
    """
    pts = []
    pitch = 2 * math.pi / teeth
    for k in range(teeth):
        a = pitch * k
        for radius, fraction in ((0.32, 0.05), (0.50, 0.15),
                                 (0.50, 0.35), (0.32, 0.45)):
            angle = a + fraction * pitch
            pts.append((radius * math.cos(angle), radius * math.sin(angle)))
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
    "cat_head": cat_head,
    "leaf": leaf, "rabbit": rabbit, "gear": gear, "plane": plane,
}

LABELS = {
    "taiwan": "台灣", "fish": "魚", "butterfly": "蝴蝶", "umbrella": "雨傘",
    "lightning": "閃電", "music_note": "音符", "house": "房子",
    "crown": "皇冠", "cup": "咖啡杯", "cat": "貓", "cat_head": "貓頭",
    "leaf": "葉子",
    "rabbit": "兔子", "gear": "齒輪",
    "plane": "飛機",
}


def install() -> list:
    """Register every shape in the pack with shape_library."""
    import routeshape.shapes.library as sl
    for name, fn in PACK.items():
        sl.register(name, fn())
    return list(PACK)


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = install()
    import routeshape.feasibility as rf
    fig, axes = plt.subplots(3, 4, figsize=(11, 9))
    print(f"{'shape':12s}{'n_min':>7}{'min km':>9}{'at 30 km':>10}")
    import routeshape.shapes.library as sl
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
