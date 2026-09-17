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

THE OUTLINE NEEDS A FEATURE NO OTHER OUTLINE HAS. This is the rule POC 32
produced, and it is the one to choose subjects by. Two raters named fifteen
shapes with no label and no reference, and the split was almost clean:

  named every time   butterfly, cup, fish, music_note, plane
  never named        crown, lightning, umbrella, rabbit, cat_head

The winners each carry one part nothing else has - a handle, a forked tail, a
cruciform, a flag, four lobes. The losers are assembled entirely from generic
parts: a zigzag (which is a mountain, or an arrow), a dome on a stick (a
mushroom, a tree), a blob with ears (any animal - and the cat's head was in
fact named as the cat). Being distinctive OVERALL is not enough and neither is
being drawn correctly; the reader needs one place to put their finger.

Per-shape accuracy varies far more than chance allows (permutation p < 0.0001)
while accuracy against shape distance is flat, so for shapes like these
recognition is decided by the drawing before any route is fitted. BACKLOG 27.

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
    wings = _sym([
        (0.10, 0.40), (0.30, 0.62), (0.50, 0.52), (0.44, 0.24), (0.22, 0.08),
        (0.10, 0.02),                                   # waist
        (0.28, -0.10), (0.40, -0.26), (0.30, -0.40), (0.34, -0.56),
        (0.16, -0.40), (0.08, -0.32),                   # lower wing + tail
    ], (0.00, 0.20), (0.00, -0.42))
    # The abdomen, as an out-and-back stroke down the middle. A rater said the
    # wings were fine and it still needed "a line from top to bottom", which is
    # the body every drawn butterfly has and a silhouette cannot show. It costs
    # 21.3 km to 34.3 - the most expensive single line in the pack - because a
    # zero-width feature is the finest feature there is and n_min tracks that.
    spine = np.array([(0.00, 0.19), (0.00, 0.06), (0.00, -0.08),
                      (0.00, -0.22), (0.00, -0.34)])
    return np.vstack([wings, spine, spine[::-1][1:]])


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
    """Overhanging eaves, a chimney, and a door that is CLOSED at the bottom.

    The plain pentagon this replaces was not wrong, it was generic. The door
    was then a notch cut up out of the base, and a rater asked for "a line under
    the door" - correctly: a notch is a hole in the wall, and a door is a
    rectangle standing on the floor. `multi_contour` makes it its own contour
    with the base running unbroken underneath, joined by a short stub. 14.0 km
    to 22.0.
    """
    from routeshape.shapes.multi_contour import merge

    walls = np.array([
        (-0.46, -0.36), (0.01, -0.36), (0.46, -0.36),   # base; the middle
        (0.46, 0.06), (0.56, 0.10),                     # vertex takes the stub
        (0.00, 0.46),                                   # ridge
        (-0.26, 0.28), (-0.26, 0.48), (-0.40, 0.48), (-0.40, 0.18),
        (-0.56, 0.10), (-0.46, 0.06),                   # chimney, eave
    ])
    door = np.array([(-0.10, -0.30), (0.12, -0.30), (0.12, -0.02), (-0.10, -0.02)])
    curve, _connector_length, _tree = merge([walls, door])
    return curve


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
    """A mug seen from the side, handle included - the handle is the giveaway.

    So the handle was doubled in thickness after a rater named it as the reason
    the cup did not read: at the first drawing it was 6% of the width, and a
    giveaway nobody can see gives nothing away. 10.7 km to 12.3.
    """
    body = [(-0.34, 0.30), (0.20, 0.30), (0.20, 0.12)]
    handle = [(0.34, 0.14), (0.48, 0.02), (0.48, -0.14), (0.34, -0.26),
              (0.20, -0.22), (0.28, -0.12), (0.28, 0.00), (0.20, 0.04)]
    rest = [(0.20, 0.00), (0.14, -0.34), (-0.28, -0.34), (-0.34, 0.00)]
    return np.array(body + handle + rest)


def leaf() -> np.ndarray:
    """An OVATE blade with a midrib and a stem: wide at the stem, tapering to a
    point.

    Drawn as a symmetric lens it was called lips, and that is exactly right -
    lips are symmetric both ways, and a leaf is symmetric only about its
    midrib. Fixing the asymmetry is the whole change and it is not a trade: the
    floor falls 20.5 km to 9.1, because a lens has two sharp tips to resolve
    and an ovate blade has one.

    THE VEINS DO NOT FIT, and two raters have now asked for them. The interior
    line is drawn the way the midrib is, by going out along it and back, and
    the cost is not the ink, it is n_min tracking the FINEST feature:

        midrib only        n_min  56   >= 21 km   (the old lens)
        1 pair of veins    n_min 136   >= 61 km
        2 pairs            n_min 188   >= 90 km
        serrated margin    n_min 128   >= 58 km   (tried in place of veins)

    A 2-pair leaf asked for at 100 km came back 79.7 km at a shape distance of
    0.250 with the veins landing as blobs, so the street network cannot draw
    them at any distance somebody will ride. The serrated margin was the same
    answer: the teeth are finer than the midrib, and fineness is what costs.
    Asymmetry is the version of "more leaf-like" that the streets can render.
    """
    def blade(sign: int) -> list:
        pts = []
        for t in np.linspace(0.04, 0.96, 9):
            x = 0.62 - 1.12 * t
            # widest a third of the way from the stem, not at the middle
            w = 0.38 * (t ** 0.55) * ((1 - t) ** 1.25) / (0.55 ** 0.55 * 0.45 ** 1.25)
            pts.append((x, sign * w))
        return pts

    return np.array(
        [(0.62, 0.00)] + blade(1)
        + [(-0.50, 0.00), (-0.66, -0.08), (-0.50, 0.00)]     # tip, STEM, back
        + list(reversed(blade(-1)))
        + [(0.62, 0.00), (-0.50, 0.00)])                     # MIDRIB, and the
                                                             # close draws it back


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


def _gear_body(teeth: int = 8) -> np.ndarray:
    pts = []
    pitch = 2 * math.pi / teeth
    for k in range(teeth):
        a = pitch * k
        for radius, fraction in ((0.32, 0.05), (0.50, 0.15),
                                 (0.50, 0.35), (0.32, 0.45)):
            angle = a + fraction * pitch
            pts.append((radius * math.cos(angle), radius * math.sin(angle)))
    return np.array(pts)


def gear(teeth: int = 8, hole: float = 0.16) -> np.ndarray:
    """Eight square teeth with flat tops and flat valleys, round a centre hole.

    Sixteen pointed teeth over a V-shaped valley is the outline of a sun, not
    of a gear, and at any rideable size they came out as noise indistinguishable
    from the street grid. Halving the count and squaring the profile doubled the
    width of every tooth and cost nothing that reads.

    That was not enough. Two rounds of blind identification named the toothed
    ring 1 time out of 6, and the complaint was the same both times: a gear has
    a HOLE. `multi_contour` puts one in - the route rides a spoke in to the bore,
    round it, and back out - and the price is the floor, 10.5 km to 22.4. A
    bigger bore at 0.20 reads better still and costs 29.1; 0.16 is the cheapest
    that is unmistakably a gear.

    Second shape here to need an interior, after the ghost, and for the same
    reason: a ring of teeth and a dome with a wavy hem are both blobs, and
    POC 20's rule that identity lives in the silhouette has exactly these
    exceptions.
    """
    from routeshape.shapes.multi_contour import merge

    body = _gear_body(teeth)
    if not hole:
        return body
    angles = np.linspace(0, 2 * math.pi, 12, endpoint=False)
    bore = np.column_stack([hole * np.cos(angles), hole * np.sin(angles)])
    curve, _connector_length, _tree = merge([body, bore])
    return curve


def plane() -> np.ndarray:
    """From above: fuselage, swept wings, tailplane."""
    right = [(0.05, 0.50), (0.09, 0.22), (0.50, -0.06), (0.50, -0.16),
             (0.09, -0.06), (0.07, -0.34), (0.24, -0.46), (0.24, -0.54),
             (0.04, -0.50)]
    pts = [(0.00, 0.56)] + right + [(0.00, -0.56)]
    pts += [(-x, y) for x, y in reversed(right)]
    return np.array(pts)


# ---------------------------------------------------------------------------
# Seasonal. Chosen by the rule POC 32 produced rather than by what looks good:
# the outline needs a feature no other outline has.
# ---------------------------------------------------------------------------
def gingerbread() -> np.ndarray:
    """A round head and four splayed limbs with rounded ends.

    The cheapest recognisable figure in the pack at 9.1 km, and the reason is
    the rule: nothing else in the world of drawable objects is a symmetric body
    with four stubby limbs stuck straight out. Compare the rabbit it replaces,
    which was a blob with ears and shared that description with every animal.
    """
    return _sym([
        (0.10, 0.54), (0.17, 0.44), (0.16, 0.30), (0.10, 0.24),      # head, neck
        (0.20, 0.20),                                                # shoulder
        (0.34, 0.24), (0.45, 0.18), (0.43, 0.05), (0.30, 0.04),      # arm
        (0.22, -0.06), (0.20, -0.22),                                # side
        (0.27, -0.36), (0.25, -0.51), (0.13, -0.55), (0.06, -0.44),  # leg
        (0.05, -0.32),
    ], (0.00, 0.58), (0.00, -0.30))


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, n: int) -> list:
    """Points on a circle, degrees clockwise from straight up."""
    return [(cx + r * math.sin(math.radians(a)), cy + r * math.cos(math.radians(a)))
            for a in np.linspace(a0, a1, n)]


def snowman() -> np.ndarray:
    """Three real circles, clipped where they actually intersect, under a hat.

    Drawn first as polygons it was called thin, then widened, and then called
    ugly - correctly: it was a column of straight edges and sharp corners, and
    everything in this pack that reads well has a round outline. Built from
    circles instead it is both better looking and CHEAPER, 18.2 km to 14.6,
    because a circle costs fewer sample points than a polygon pretending to be
    one.

    The waists are the diagnostic feature. The centres are spaced so the
    circles overlap only a little - at the first spacing tried they met at
    almost the full head radius and there was no waist at all. No arms: a stick
    arm is a stroke, and strokes are the one thing this project has never
    managed to draw (BACKLOG 26).
    """
    return _sym(
        [(0.15, 0.86), (0.15, 0.68),                       # hat crown
         (0.30, 0.66), (0.31, 0.60), (0.17, 0.58)]         # brim
        + _arc(0.00, 0.46, 0.20, 55, 136, 5)               # head
        + _arc(0.00, 0.06, 0.29, 28, 121, 6)               # middle
        + _arc(0.00, -0.40, 0.40, 39, 168, 8),             # bottom
        (0.00, 0.86), (0.00, -0.80))


def christmas_tree() -> np.ndarray:
    """Tiers over a trunk, under a five-pointed star.

    The tiers alone are a mountain range - precisely how the crown failed, 0/4
    with every rater saying "cannot tell" - and the trunk is what a mountain has
    not got. But a tree with a trunk is still only a tree; the star is what
    makes it THIS tree, and it was added after the first draft was called clear
    and not Christmas.

    The star has to be coarse. A finely drawn one took the floor to 38.6 km on
    its own; five big points at a fifth of the tree's width cost 18.3.
    """
    return _sym(
        [(0.06, 0.72), (0.21, 0.71), (0.10, 0.61), (0.13, 0.46)]   # star
        + [(0.25, 0.36), (0.14, 0.30),
           (0.36, 0.16), (0.23, 0.09),
           (0.47, -0.08), (0.33, -0.15),
           (0.58, -0.32), (0.13, -0.32),
           (0.13, -0.60)],                                         # TRUNK
        (0.00, 0.86), (0.00, -0.60))


def _ghost_body() -> np.ndarray:
    return _sym([
        (0.16, 0.44), (0.28, 0.34), (0.32, 0.16),         # dome
        (0.44, 0.10), (0.44, -0.02), (0.33, -0.06),       # stub arm
        (0.34, -0.34),
        (0.28, -0.50), (0.18, -0.34), (0.08, -0.50),      # hem
    ], (0.00, 0.50), (0.00, -0.34))


def ghost() -> np.ndarray:
    """A dome, two stub arms, a hem of deep waves - and two eyes.

    The body alone scores 0.354 on `metrics.thinness`, the highest of anything
    here, and it was still unreadable: "really cannot tell, probably because it
    has no eyes". A ghost is the one subject in this pack whose identity is not
    in its silhouette at all - a dome with a wavy hem is a blob - so it is the
    one place the interior is worth paying for.

    `multi_contour` carries the eyes into the single closed curve, and the price
    is the floor: 13.8 km to 27.6. Cheaper than it was for the cat's face
    (7.8 -> 34.3) because the connectors here run horizontally into the eyes
    from the arms rather than diagonally across a cheek, which is also why they
    do not read as a scar.
    """
    from routeshape.shapes.multi_contour import merge

    def eye(cx):
        a = np.linspace(0, 2 * math.pi, 10, endpoint=False)
        return np.column_stack([cx + 0.08 * np.cos(a), 0.16 + 0.10 * np.sin(a)])

    curve, _connector_length, _tree = merge([_ghost_body(), eye(-0.15), eye(0.15)])
    return curve


def bat() -> np.ndarray:
    """Spread wings with a scalloped trailing edge.

    The scallops are the identity, not the ears - a first draft gave the ears
    half the height of the head and the two spikes read as two more wing
    fingers. Thinness 0.100 sits exactly on the warning line because the
    scallops are deep; that is the feature, so it is accepted here and noted.
    """
    return _sym([
        (0.09, 0.32), (0.15, 0.46), (0.21, 0.30),         # ear
        (0.26, 0.22), (0.34, 0.28),                       # head, shoulder
        (0.52, 0.38), (0.70, 0.36), (0.82, 0.26),         # leading edge
        (0.70, 0.10), (0.60, 0.22),                       # finger, scallop
        (0.48, 0.00), (0.38, 0.14),                       # finger, scallop
        (0.28, -0.08),                                    # finger into the body
        (0.17, -0.04), (0.14, -0.22), (0.07, -0.32),      # body, foot
    ], (0.00, 0.34), (0.00, -0.36))


def witch_hat() -> np.ndarray:
    """An upright cone on a wide, DEEP brim.

    Drawn leaning, as a witch's hat usually is, it read as a boot - and so did
    three drafts of a Santa hat, which was abandoned for the same reason. A
    tilted cone rising from a horizontal base IS the profile of a boot. Upright
    and symmetric it is a hat again, and the brim is what separates it from a
    party hat, so the brim was then deepened until it reads as one: 0.28 of the
    height rather than 0.20.

    The cheapest shape in the pack at 5.0 km - a city ride draws it.
    """
    return _sym([
        (0.10, 0.28), (0.17, -0.02), (0.22, -0.18),       # cone
        (0.46, -0.22), (0.44, -0.46),                     # BRIM
        (0.14, -0.48),
    ], (0.00, 0.62), (0.00, -0.48))


# Retired by measurement, not by taste. POC 32 put every shape in front of two
# raters with no label and no reference; these five were named correctly ZERO
# times out of four, at every distance the router can reach - including their
# own closest fit. Four of them had been redrawn and approved by eye the week
# before, which is the whole reason the task exists.
#
# The code stays. What each one lacked is a usable finding and deleting it
# would throw that away, and a redraw that gives one a diagnostic feature can
# put it back in PACK.
#
#   crown      a zigzag on a trapezoid, which is a mountain range
#   lightning  a zigzag, which is an arrow
#   umbrella   a dome on a stick, which is a mushroom, or a tree
#   rabbit     a blob with ears, which is any animal
#   cat_head   a blob with ears - and its one misidentification was as `cat`
RETIRED = {
    "crown": crown, "lightning": lightning, "umbrella": umbrella,
    "rabbit": rabbit, "cat_head": cat_head,
}

PACK = {
    "taiwan": taiwan, "fish": fish, "butterfly": butterfly,
    "music_note": music_note, "house": house, "cup": cup, "cat": cat,
    "leaf": leaf, "gear": gear, "plane": plane,
    # Seasonal, and untested - they go into the next blind round.
    "gingerbread": gingerbread, "snowman": snowman,
    "christmas_tree": christmas_tree,
    "ghost": ghost, "bat": bat, "witch_hat": witch_hat,
}

LABELS = {
    "taiwan": "台灣", "fish": "魚", "butterfly": "蝴蝶",
    "music_note": "音符", "house": "房子", "cup": "咖啡杯", "cat": "貓",
    "leaf": "葉子", "gear": "齒輪", "plane": "飛機",
    "gingerbread": "薑餅人", "snowman": "雪人", "christmas_tree": "聖誕樹",
    "ghost": "鬼", "bat": "蝙蝠", "witch_hat": "女巫帽",
}
RETIRED_LABELS = {
    "crown": "皇冠", "lightning": "閃電", "umbrella": "雨傘",
    "rabbit": "兔子", "cat_head": "貓頭",
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
