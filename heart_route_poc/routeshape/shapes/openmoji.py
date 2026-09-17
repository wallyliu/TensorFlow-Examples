"""
Outlines from OpenMoji's SVG, where the lines a person draws are already lines.

The bitmap tracer (shapes.emoji) works and is blind to exactly one thing: the
interior. An emoji is an opaque picture, so a ghost's eyes and an elephant's ear
are painted rather than absent, and BACKLOG 41 records three failed attempts to
recover them from colour regions in a 109 px render.

OpenMoji ships SVG, and its files are built the way the drawing was made:

    <g id="color">   filled closed paths - the body, and separately the eyes,
                     the pupils, any part drawn in its own colour
    <g id="line">    open strokes - the ear line, the mouth, the fold of a wing

So the interior is not inferred here, it is read. The body is the largest
closed filled path; closed paths inside it become contours merged in the way
`multi_contour` merges any hole; open strokes inside it become out-and-back
excursions, the same construction the leaf's midrib uses.

WHY OPENMOJI AND NOT TWEMOJI. Twemoji is also SVG and also free, but it draws
in flat shapes with no line layer, so the ear is a colour boundary again.
OpenMoji separates them because it ships a black line-art variant.

AND WHY NOT NOTO, which is what POC 36 measured. Noto is the bitmap font on
this machine, and the raters grew up on Apple's emoji, so POC 36's traced-beats-
hand-drawn (p = 0.016) was won with a set nobody in the test uses. That makes
the result conservative, and it makes the question of WHICH set reads best an
open one - this module is what lets it be asked.

Licence: OpenMoji is CC BY-SA 4.0. Attribution belongs in anything published
from these outlines.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from routeshape.paths import PROJECT_ROOT

SOURCE = ("https://raw.githubusercontent.com/hfg-gmuend/openmoji/master"
          "/color/svg/{code}.svg")
CACHE = PROJECT_ROOT / "_openmoji"
FLATTEN = 400          # samples per path when turning curves into polylines
TOLERANCE = 0.008      # of the shape's width, as in shapes.emoji
MAX_VERTICES = 150
MIN_HOLE_AREA = 0.004  # of the body, so a pupil survives and a speck does not
STROKE_INSET = 0.030
MIN_LINE_LENGTH = 0.18     # of the body's width; shorter is a whisker
TOUCH = 0.012          # of the body's width; a detail edge this close to the
                       # silhouette IS the silhouette, redrawn
DUPLICATE = 0.02       # of the body's width; two lines this close are one line


def codepoint(emoji: str) -> str:
    """OpenMoji's file name: hyphenated hex, upper case, no VS16."""
    return "-".join(f"{ord(c):04X}" for c in emoji if ord(c) != 0xFE0F)


def fetch(emoji: str) -> Path:
    code = codepoint(emoji)
    CACHE.mkdir(exist_ok=True)
    local = CACHE / f"{code}.svg"
    if not local.exists():
        import urllib.request
        with urllib.request.urlopen(SOURCE.format(code=code), timeout=30) as r:
            local.write_bytes(r.read())
    return local


def _polylines(svg: Path) -> tuple[list, list]:
    """(closed filled polygons, open stroked polylines), y already flipped."""
    import svgpathtools as sp

    paths, attrs = sp.svg2paths(str(svg))
    closed, strokes = [], []
    pieces = []
    for path, attr in zip(paths, attrs):
        # A <path> may hold several subpaths (the gear's ring is drawn as one
        # element with a discontinuity between the bore and the rim), and
        # svgpathtools asserts rather than answers when asked whether such a
        # path is closed. Split first, ask after.
        try:
            subs = path.continuous_subpaths()
        except Exception:
            subs = [path]
        pieces += [(sub, attr) for sub in subs]
    for path, attr in pieces:
        if len(path) == 0:
            continue
        pts = np.array([path.point(t) for t in np.linspace(0, 1, FLATTEN)])
        xy = np.column_stack([pts.real, -pts.imag])       # SVG y points down
        filled = attr.get("fill", "none") not in ("none", None, "")
        # A filled path is a region whether or not it says `z`: SVG closes it
        # to fill it, and OpenMoji's sauropod is one long unclosed path with a
        # fill colour. Asking isclosed() first threw that whole body away.
        if filled:
            closed.append(xy)
        elif not path.isclosed():
            strokes.append(xy)
    return closed, strokes



def _longest_run(flags: np.ndarray) -> slice | None:
    """The longest unbroken stretch of True, as a slice."""
    best, best_len, start = None, 0, None
    for i, on in enumerate(flags):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start > best_len:
                best, best_len = slice(start, i), i - start
            start = None
    if start is not None and len(flags) - start > best_len:
        best, best_len = slice(start, len(flags)), len(flags) - start
    return best if best_len >= 8 else None


def _area(xy: np.ndarray) -> float:
    x, y = xy[:, 0], xy[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2


CONTAINED = 0.98       # of a path's own area; that much inside a bigger piece
                       # makes it a detail drawn ON the silhouette, not part of it


def _parts(closed: list) -> tuple[list, list]:
    """Split the filled paths into the pieces of the silhouette and the
    details drawn on top of it.

    OpenMoji composes a figure from several filled paths - the crab is a shell
    plus eight legs plus two claws - so taking only the largest one leaves a
    featureless blob. A path that sticks out of everything bigger than it is
    another PIECE and belongs in the union; a path that sits wholly inside one
    is a DETAIL - an eye, a pupil, a spot - and has to stay a separate contour
    or the union would swallow it.
    """
    from shapely.geometry import Polygon

    polys = []
    for xy in closed:
        poly = Polygon(xy).buffer(0)
        if not poly.is_empty and poly.area > 0:
            polys.append(poly)
    polys.sort(key=lambda p: p.area, reverse=True)

    pieces, details = [], []
    for poly in polys:
        covered = max((p.intersection(poly).area for p in pieces), default=0.0)
        if covered >= CONTAINED * poly.area:
            details.append(poly)
        else:
            pieces.append(poly)
    # A pupil inside an eye is inside the body too. Keep the outermost detail
    # only - one ring reads as an eye, two rings read as a target.
    top = [d for d in details
           if not any(o is not d and o.area > d.area
                      and o.intersection(d).area >= CONTAINED * d.area
                      for o in details)]
    return pieces, top


def _open_part(ring, edge, span):
    """The part of a detail's outline that is not the silhouette redrawn.

    OpenMoji shades a figure by filling a region bounded on one side by the
    silhouette itself: the snowman's two crescents are the shadowed halves of
    its two balls, and the door of the house sits on the ground line. Kept as
    closed contours they retrace the outline a hair inside it and cross it
    wherever simplification moves either one. What is worth drawing is the
    boundary they DON'T share - the fold, the three sides of the doorway - so
    cut the shared part away and keep the rest as a line.

    Returns (piece, is_ring): the whole ring when it touches nothing.
    """
    from shapely.geometry import LineString

    rest = ring.difference(edge.buffer(TOUCH * span))
    if rest.is_empty:
        return None, False
    parts = list(getattr(rest, "geoms", [rest]))
    longest = max(parts, key=lambda g: g.length)
    if longest.length >= 0.95 * ring.length:
        return None, True
    return np.array(LineString(longest).coords), False


def _fresh(arc, kept, span):
    """False if this line is one already taken, drawn a second time.

    OpenMoji's fish has its gill arc in both the colour layer and the line
    layer, a few tenths of a percent apart. Two copies of one curve cross each
    other at every wobble - eight times, in that fish.
    """
    from shapely.geometry import LineString

    a = LineString(arc)
    return all(a.hausdorff_distance(LineString(k)) > DUPLICATE * span
               for k in kept)


def outline(emoji: str, tolerance: float = TOLERANCE,
            max_vertices: int = MAX_VERTICES, interior: bool = True) -> np.ndarray:
    """One emoji's drawing - silhouette, inner shapes and inner lines - as one
    closed curve, normalised to unit width and centred."""
    from shapely.geometry import LinearRing, LineString, Point
    from shapely.ops import unary_union
    from routeshape.shapes.multi_contour import merge

    closed, strokes = _polylines(fetch(emoji))
    if not closed:
        msg = f"no filled closed path in OpenMoji {codepoint(emoji)}"
        raise ValueError(msg)

    parts, details = _parts(closed)
    shell = unary_union(parts).buffer(0)
    blobs = sorted(getattr(shell, "geoms", [shell]), key=lambda g: g.area,
                   reverse=True)
    body = np.array(blobs[0].exterior.coords)[:-1]
    span = float(max(body.max(axis=0) - body.min(axis=0)))
    floor = MIN_HOLE_AREA * blobs[0].area
    edge = LineString(blobs[0].exterior.coords)

    rings, lines = [], []
    # A piece the union left detached (a floating antenna) is still part of the
    # drawing, and a hole the union opened up (the gap under a handle) is the
    # thing that makes a cup a cup. Both are contours in exactly the same way.
    rings += [np.array(g.exterior.coords)[:-1] for g in blobs[1:]
              if g.area >= floor]
    rings += [np.array(r.coords)[:-1] for r in blobs[0].interiors
              if _area(np.array(r.coords)) >= floor]
    if interior:
        for d in sorted(details, key=lambda d: d.area, reverse=True):
            if d.area < floor:
                continue
            piece, whole = _open_part(LineString(d.exterior.coords), edge, span)
            if whole:
                rings.append(np.array(d.exterior.coords)[:-1])
            elif piece is not None and LineString(piece).length >= MIN_LINE_LENGTH * span:
                lines.append(piece)

    deep = blobs[0].buffer(-STROKE_INSET * span)
    if interior and not deep.is_empty:
        for stroke in strokes:
            inside = np.array([deep.contains(Point(x, y)) for x, y in stroke])
            # A whole stroke is the wrong unit. OpenMoji draws the elephant's
            # SILHOUETTE AND ITS EAR as one continuous path, so 28% of that
            # stroke is the line we want and 72% is the outline we already have.
            # Take the longest unbroken interior run instead.
            run = _longest_run(inside)
            if run is None:
                continue
            piece = stroke[run]
            length = float(np.hypot(*np.diff(piece, axis=0).T).sum())
            if length >= MIN_LINE_LENGTH * span and _fresh(piece, lines, span):
                lines.append(piece)
    lines.sort(key=lambda a: -float(np.hypot(*np.diff(a, axis=0).T).sum()))

    # Add one feature at a time and keep it only if the curve is still simple.
    # A crossing is fatal downstream - describe.check refuses the shape and the
    # route never gets built - and it is never worth losing the whole drawing
    # to keep one line. Longest first, so what survives is the boldest mark.
    def build(rs, ls):
        return _assemble(body, rs, ls, span, tolerance, max_vertices, merge)

    def simple(curve):
        from routeshape.describe import self_intersections
        return not self_intersections(curve)

    keep_r: list = []
    for ring in rings:
        if simple(build(keep_r + [ring], [])):
            keep_r.append(ring)
    keep_l: list = []
    for line in lines:
        if simple(build(keep_r, keep_l + [line])):
            keep_l.append(line)
    return build(keep_r, keep_l)


def _assemble(body, inner, lines, span, tolerance, max_vertices, merge):
    from shapely.geometry import LineString, Polygon

    def simplify(xy, closed_ring):
        if closed_ring:
            poly = Polygon(xy).buffer(0)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda g: g.area)
            return np.array(poly.simplify(tolerance * span).exterior.coords)[:-1]
        return np.array(LineString(xy).simplify(tolerance * span).coords)

    while True:
        rings = [simplify(body, True)] + [simplify(c, True) for c in inner]
        curve = rings[0] if len(rings) == 1 else merge(rings)[0]
        for line in lines:
            arc = simplify(line, False)
            if len(arc) < 3:
                continue
            # Splice as an out-and-back, and COME BACK TO THE JOIN before
            # carrying on. Leaving that last return out is what made the first
            # attempt at this cross its own closing segment: the path jumped
            # from the start of the stroke straight to the next outer vertex.
            j = int(np.argmin(np.hypot(curve[:, 0] - arc[0, 0],
                                       curve[:, 1] - arc[0, 1])))
            curve = np.vstack([curve[:j + 1], arc, arc[::-1][1:],
                               curve[j:j + 1], curve[j + 1:]])
        if len(curve) <= max_vertices or tolerance >= 0.06:
            break
        tolerance *= 1.3

    curve = curve - curve.mean(axis=0)
    return curve / float(max(curve.max(axis=0) - curve.min(axis=0)))


def install(prefix: str = "o_", names: list | None = None) -> list:
    """Register OpenMoji outlines with shape_library, under a prefix.

    Same subjects and same labels as `shapes.emoji` - the two modules are two
    DRAWINGS of one list, which is the whole point of having both - so the pack
    is imported rather than restated.
    """
    import routeshape.shapes.library as sl
    from routeshape.shapes.emoji import PACK

    installed = []
    for name, (character, _label) in PACK.items():
        if names is not None and name not in names:
            continue
        try:
            sl.register(prefix + name, outline(character))
        except Exception as exc:      # noqa: BLE001 - one bad glyph is not fatal
            print(f"  {name}: {exc}")
            continue
        installed.append(prefix + name)
    return installed
