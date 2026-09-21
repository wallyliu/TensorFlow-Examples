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

# WHERE THE FONT IS depends on the machine, and hard-coding Debian's path meant
# that on any other one every trace failed - and the page reported it as
# 「找不到披薩」, which is a lie: the emoji was found, it could not be DRAWN.
# Searched in order, and `ROUTESHAPE_EMOJI_FONT` wins so a rider with the font
# somewhere unusual has a way in.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji_WindowsCompatible.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/usr/local/share/fonts/NotoColorEmoji.ttf",
    str(Path.home() / ".local/share/fonts/NotoColorEmoji.ttf"),
    str(Path.home() / ".fonts/NotoColorEmoji.ttf"),
)
INSTALL_HINT = ("找不到 Noto Color Emoji 字型。"
                "Debian/Ubuntu: sudo apt install fonts-noto-color-emoji；"
                "或把字型路徑放進 ROUTESHAPE_EMOJI_FONT 環境變數。")


def find_font() -> Path:
    """The emoji font on this machine, or a message saying how to get one.

    Noto specifically: the tracer reads a bitmap strike at `PX`, which is the
    one size this font carries. Apple's and Microsoft's emoji fonts are built
    differently and would need a different reader, so pointing this at them
    would fail later and less clearly than failing here.
    """
    import os

    override = os.environ.get("ROUTESHAPE_EMOJI_FONT")
    if override and Path(override).exists():
        return Path(override)
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return Path(path)
    import glob
    for root in ("/usr/share/fonts", "/usr/local/share/fonts",
                 str(Path.home() / ".local/share/fonts")):
        found = glob.glob(root + "/**/NotoColorEmoji*.ttf", recursive=True)
        if found:
            return Path(sorted(found)[0])
    raise FileNotFoundError(INSTALL_HINT)


def _font_path() -> Path:
    global FONT
    if FONT is None:
        FONT = find_font()
    return FONT


FONT: Path | None = None
try:
    FONT = find_font()
except FileNotFoundError:
    pass                      # reported when something actually asks to draw
PX = 109                    # the only bitmap strike the font carries
TOLERANCE = 0.008           # of the shape's width
MAX_VERTICES = 150          # describe.check refuses above 160
ALPHA = 128
MIN_HOLE_AREA = 0.012      # of the body, so speckle is not a bore


def _mask(emoji: str) -> tuple[np.ndarray, list]:
    """The glyph's largest solid region, and the holes worth keeping in it.

    Filling every hole was the first version and it threw away the two interior
    features this project had already learned to pay for by hand: the gear's
    bore and the ghost's eyes. A gear without a bore was named 1 time in 6
    (POC 33) and a ghost without eyes 0 in 4, and both were fixed by putting the
    interior back with `multi_contour`. The tracer should not be undoing that.

    ONLY TRANSPARENT HOLES ARE FOUND, and that is most of them missed. An emoji
    is an opaque picture: the gear's bore is a real gap and comes back, and so
    is the gap inside a cup's handle, but the ghost's eyes and a doughnut's hole
    are PAINTED - dark pixels, not absent ones - so alpha cannot see them. Of
    twelve glyphs traced for the round-four pairs, two had a hole. Finding the
    rest means segmenting by colour, which is a different and much less robust
    program, and it is not attempted here.
    """
    from PIL import Image, ImageDraw, ImageFont
    from scipy import ndimage

    font = ImageFont.truetype(str(_font_path()), PX)
    img = Image.new("RGBA", (PX * 3, PX * 3), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((PX, PX), emoji, font=font, embedded_color=True)
    mask = np.array(img)[:, :, 3] > ALPHA
    if not mask.any():
        msg = f"no glyph for {emoji!r} in {_font_path().name}"
        raise ValueError(msg)
    filled = ndimage.binary_fill_holes(mask)
    labels, count = ndimage.label(filled)
    sizes = ndimage.sum(filled, labels, range(1, count + 1))
    body = labels == (int(np.argmax(sizes)) + 1)

    hole_map, holes = ndimage.label(body & ~mask)
    if holes == 0:
        return body, []
    floor = MIN_HOLE_AREA * float(body.sum())
    kept = [hole_map == (i + 1)
            for i, area in enumerate(ndimage.sum(body & ~mask, hole_map,
                                                 range(1, holes + 1)))
            if area >= floor]
    return body, kept


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
            max_vertices: int = MAX_VERTICES, holes: bool = True) -> np.ndarray:
    """One emoji's silhouette, normalised to unit width and centred.

    Holes big enough to matter are carried in as separate contours and merged
    into the single closed curve the rest of the pipeline wants - the route
    rides a spoke in, round the hole, and back out, exactly as the hand-built
    gear bore and ghost eyes do.

    The tolerance is loosened, never tightened, if the trace comes out with
    more vertices than the pipeline accepts - a cap is a cap, and coarsening is
    the only lever that respects it.
    """
    from routeshape.shapes.multi_contour import merge

    body, inner = _mask(emoji)
    contours = [_trace(body)] + ([_trace(h) for h in inner] if holes else [])
    span = float(max(contours[0].max(axis=0) - contours[0].min(axis=0)))
    while True:
        simple = [_simplify(c, tolerance * span / max(
            1e-9, float(max(c.max(axis=0) - c.min(axis=0))))) for c in contours]
        points = simple[0] if len(simple) == 1 else merge(simple)[0]
        if len(points) <= max_vertices or tolerance >= 0.06:
            break
        tolerance *= 1.3
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
    # 雷龍 and not 恐龍: the hand-drawn trex is already 恐龍, and two options
    # reading the same word is a question a rater cannot answer. Round five
    # shipped with both for one build because this rename lived in the server
    # instead of here, where every consumer sees it.
    "crab": ("🦀", "螃蟹"), "sauropod": ("🦕", "雷龍"),
    "whale": ("🐳", "鯨魚"), "mushroom": ("🍄", "蘑菇"),
    "maple": ("🍁", "楓葉"), "cactus": ("🌵", "仙人掌"),
    "apple": ("🍎", "蘋果"), "butterfly": ("🦋", "蝴蝶"),
    "bicycle": ("🚲", "腳踏車"), "rocket": ("🚀", "火箭"),
    "anchor": ("⚓", "錨"), "guitar": ("🎸", "吉他"),
    # The twins of what is left of the hand-drawn pack, for round four.
    "bat": ("🦇", "蝙蝠"), "cat": ("🐈", "貓"),
    "christmas_tree": ("🎄", "聖誕樹"), "cup": ("☕", "咖啡杯"),
    "fish": ("🐟", "魚"), "gear": ("⚙", "齒輪"), "ghost": ("👻", "鬼"),
    "house": ("🏠", "房子"), "leaf": ("🍃", "葉子"),
    "music_note": ("🎵", "音符"), "plane": ("✈", "飛機"),
    "snowman": ("⛄", "雪人"),
}
LABELS = {name: label for name, (_, label) in PACK.items()}


def install(prefix: str = "e_", names: list | None = None) -> list:
    """Register every emoji shape with shape_library, under a prefix.

    Prefixed because several of these share a name with a hand-drawn shape -
    elephant, crab, giraffe, maple, butterfly - and the point of keeping both
    is to put them in front of raters together.
    """
    import routeshape.shapes.library as sl

    installed, failed = [], []
    for name, (character, _label) in PACK.items():
        if names is not None and name not in names:
            continue
        try:
            sl.register(prefix + name, outline(character))
        except Exception as exc:      # noqa: BLE001 - one bad glyph is not fatal
            failed.append((name, str(exc)))
            continue
        installed.append(prefix + name)
    if failed:
        # ONE LINE, NOT ONE PER SHAPE. A missing font fails every glyph for the
        # same reason, and eleven identical paragraphs buried the one line that
        # says what to do about it.
        reasons = {reason for _, reason in failed}
        if len(reasons) == 1:
            print(f"  {len(failed)} emoji shapes not installed: {failed[0][1]}")
        else:
            for name, reason in failed:
                print(f"  {name}: {reason}")
    return installed
