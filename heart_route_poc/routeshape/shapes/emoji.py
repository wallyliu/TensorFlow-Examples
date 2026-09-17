"""
Outlines traced from emoji, because hand-drawing them did not work.

Seventeen hand-drawn shapes were rejected on sight by the people who looked at
them, against five that passed. BACKLOG 24's rule is right - draw the picture
people would draw, not the object - but the hand doing the drawing was mine,
and it does not know what people draw. The emoji is that picture, agreed by
committee and shipped on every phone.

Noto Color Emoji is a BITMAP font, so there is no outline to read out of it.
The silhouette is traced from the rendered glyph instead:

    render -> alpha > 128 -> fill holes -> largest connected component
    -> Moore-neighbour boundary trace -> Douglas-Peucker

SIMPLIFY TO A TOLERANCE, NOT TO A VERTEX COUNT. A fixed budget spends the same
44 points on a mushroom and a crab, which over-describes one and ruins the
other. A tolerance - "stay within this fraction of the shape's width" - lets
the count follow the subject, which at 1% is 28 points for a mushroom and 97
for a crab.

AND FINER IS USUALLY CHEAPER, which is not the obvious way round. Tracing the
elephant at 0.7% instead of 3% takes 32 points to 78 and the floor 27 km DOWN
to 20; the crab goes 56 -> 128 points and 64 km -> 46. `n_min` measures
sampling error, and a coarse polygon is long straight runs meeting at sharp
corners - which needs MORE samples to reproduce than a smooth curve does. So
there is no distance argument for tracing coarsely, only a vertex cap.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

FONT = Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf")
PX = 109                    # the only bitmap strike the font carries
TOLERANCE = 0.008           # of the shape's width
MAX_VERTICES = 150          # describe.check refuses above 160
ALPHA = 128


def _mask(emoji: str) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    from scipy import ndimage

    font = ImageFont.truetype(str(FONT), PX)
    img = Image.new("RGBA", (PX * 3, PX * 3), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((PX, PX), emoji, font=font, embedded_color=True)
    mask = np.array(img)[:, :, 3] > ALPHA
    if not mask.any():
        msg = f"no glyph for {emoji!r} in {FONT.name}"
        raise ValueError(msg)
    mask = ndimage.binary_fill_holes(mask)
    labels, count = ndimage.label(mask)
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    return labels == (int(np.argmax(sizes)) + 1)


def _trace(mask: np.ndarray) -> np.ndarray:
    """Moore-neighbour boundary following, one pixel at a time."""
    pad = np.pad(mask, 1)
    rows = np.nonzero(pad)[0]
    top = int(rows.min())
    start = (top, int(np.nonzero(pad[top])[0].min()))
    step = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    path, here, back = [start], start, 6
    while len(path) < 40000:
        for turn in range(8):
            d = (back + 1 + turn) % 8
            nxt = (here[0] + step[d][0], here[1] + step[d][1])
            if pad[nxt]:
                back, here = (d + 5) % 8, nxt
                break
        else:
            break
        if here == start:
            break
        path.append(here)
    pixels = np.array(path, dtype=float)
    return np.column_stack([pixels[:, 1], -pixels[:, 0]])     # x right, y up


def _simplify(points: np.ndarray, tolerance: float) -> np.ndarray:
    from shapely.geometry import Polygon

    poly = Polygon(points).buffer(0)
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda part: part.area)
    span = float(max(points.max(axis=0) - points.min(axis=0)))
    return np.array(poly.simplify(tolerance * span).exterior.coords)[:-1]


def outline(emoji: str, tolerance: float = TOLERANCE,
            max_vertices: int = MAX_VERTICES) -> np.ndarray:
    """One emoji's silhouette, normalised to unit width and centred.

    The tolerance is loosened, never tightened, if the trace comes out with
    more vertices than the pipeline accepts - a cap is a cap, and coarsening is
    the only lever that respects it.
    """
    raw = _trace(_mask(emoji))
    points = _simplify(raw, tolerance)
    while len(points) > max_vertices and tolerance < 0.06:
        tolerance *= 1.3
        points = _simplify(raw, tolerance)
    points = points - points.mean(axis=0)
    return points / float(max(points.max(axis=0) - points.min(axis=0)))


# The ones that came out recognisable on sight. Octopus and bee were traced and
# dropped - the octopus's arms tangle into each other and the bee reads as a
# bird - which is the same judgement every shape here gets and no better.
#
# The floors run 5 to 56 km and that is a FEATURE, not something to file down.
# The rider this is being built for said a 3 to 8 km ride is too short, so the
# cheap end is the part that needs a reason to exist, not the expensive end.
PACK = {
    "elephant": ("🐘", "大象"), "giraffe": ("🦒", "長頸鹿"),
    "penguin": ("🐧", "企鵝"), "turtle": ("🐢", "烏龜"),
    "crab": ("🦀", "螃蟹"), "sauropod": ("🦕", "恐龍"),
    "whale": ("🐳", "鯨魚"), "mushroom": ("🍄", "蘑菇"),
    "maple": ("🍁", "楓葉"), "cactus": ("🌵", "仙人掌"),
    "apple": ("🍎", "蘋果"), "butterfly": ("🦋", "蝴蝶"),
    "bicycle": ("🚲", "腳踏車"), "rocket": ("🚀", "火箭"),
    "anchor": ("⚓", "錨"), "guitar": ("🎸", "吉他"),
}
LABELS = {name: label for name, (_, label) in PACK.items()}


def install(prefix: str = "e_") -> list:
    """Register every emoji shape with shape_library, under a prefix.

    Prefixed because several of these share a name with a hand-drawn shape -
    elephant, crab, giraffe, maple, butterfly - and the point of keeping both
    is to put them in front of raters together.
    """
    import routeshape.shapes.library as sl

    installed = []
    for name, (character, _label) in PACK.items():
        try:
            sl.register(prefix + name, outline(character))
        except Exception as exc:      # noqa: BLE001 - one bad glyph is not fatal
            print(f"  {name}: {exc}")
            continue
        installed.append(prefix + name)
    return installed
