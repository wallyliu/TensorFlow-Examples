"""
Join several closed contours into ONE closed curve, so a multi-part figure
(a word, a face with eyes) can go through the existing single-curve pipeline
unchanged.

The construction is the pen that cannot lift: link the contours with the
shortest possible connectors, then walk every contour once, detouring into each
neighbour at its connector and coming straight back. Each connector is therefore
travelled twice and appears on the map as one thin line between the parts.

This is what makes the rest of the project apply as-is. shape_distance,
sampling_loss, n_min, the coarse scan and the Viterbi fit all assume a single
closed curve; none of them needs to know the curve used to be eight pieces. The
reference template is built from the SAME merged curve, so a route is never
penalised for riding a connector that was asked for on purpose.

What it does not buy is distance. Merging is cheap - the connectors add 5.6% of
perimeter for LIT, 6.1% for LOVE, 10.0% for TAIPEI - but a word is wide and
short, its strokes sit close together, and n_min climbs with the number of
features, not with the number of contours. Measured: LIT n_min 84, LOVE 160,
TAIPEI 240, which at the bike street scale is 30 / 56 / 85 km.
"""

from __future__ import annotations

import numpy as np


def densify(contour: np.ndarray, step: float) -> np.ndarray:
    """Resample a closed contour at a fixed arc-length step."""
    closed = np.vstack([contour, contour[:1]])
    seg = np.hypot(*np.diff(closed, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.arange(0.0, s[-1], step)
    return np.column_stack([np.interp(t, s, closed[:, 0]), np.interp(t, s, closed[:, 1])])


def _tangents(contour: np.ndarray) -> np.ndarray:
    """Unit direction of the curve at each point, by central difference."""
    d = np.roll(contour, -1, axis=0) - np.roll(contour, 1, axis=0)
    n = np.hypot(d[:, 0], d[:, 1])
    n[n == 0] = 1.0
    return d / n[:, None]


def closest_pair(a: np.ndarray, b: np.ndarray) -> tuple[int, int, float]:
    """Indices of the nearest point on each contour, and the distance."""
    d = np.hypot(a[:, None, 0] - b[None, :, 0], a[:, None, 1] - b[None, :, 1])
    i, j = np.unravel_index(np.argmin(d), d.shape)
    return int(i), int(j), float(d[i, j])


def best_pair(a: np.ndarray, b: np.ndarray, collinearity_weight: float,
              stride: int = 4) -> tuple[int, int, float, float]:
    """
    The connector between two contours that is short AND does not read as a stroke.

    Nearest-point is the wrong objective on thin drawings. The shortest link
    between the I's top bar and the T's top bar is horizontal, which is exactly
    the direction both bars run, so the three fuse into one long bar and the
    letters are lost. Penalising that costs a little length and buys back the
    reading.

    Ambiguity is `max(|u . t_a|, |u . t_b|)` where u is the connector direction
    and t the curve's tangent at each end: 1 when the connector continues a
    stroke, 0 when it meets it square. Cost is `length * (1 + w * ambiguity^2)`,
    so a connector is only allowed to look like a stroke if the alternatives are
    much longer.

    Returns (index into a, index into b, geometric length, cost).
    """
    ia = np.arange(0, len(a), stride)
    ib = np.arange(0, len(b), stride)
    pa, pb = a[ia], b[ib]
    ta, tb = _tangents(a)[ia], _tangents(b)[ib]

    delta = pb[None, :, :] - pa[:, None, :]
    length = np.hypot(delta[:, :, 0], delta[:, :, 1])
    safe = np.where(length == 0, 1.0, length)
    u = delta / safe[:, :, None]

    align_a = np.abs(u[:, :, 0] * ta[:, None, 0] + u[:, :, 1] * ta[:, None, 1])
    align_b = np.abs(u[:, :, 0] * tb[None, :, 0] + u[:, :, 1] * tb[None, :, 1])
    ambiguity = np.maximum(align_a, align_b)

    cost = length * (1.0 + collinearity_weight * ambiguity ** 2)
    cost[length == 0] = 0.0
    i, j = np.unravel_index(np.argmin(cost), cost.shape)
    return int(ia[i]), int(ib[j]), float(length[i, j]), float(cost[i, j])


def connector_tree(contours: list[np.ndarray],
                   collinearity_weight: float = 0.0
                   ) -> list[tuple[int, int, float, int, int]]:
    """
    Minimum spanning tree over the contours.

    A tree, not a tour: a tree is the shortest set of links that leaves nothing
    stranded, and since every link is ridden out and back anyway, closing it into
    a tour would only add length.

    `collinearity_weight` 0 reproduces plain nearest-point linking, which is
    right for outlines - a bridge between two closed letterforms reads as a
    bridge whatever its angle. Raise it for thin drawings, where a connector is
    made of the same stuff as the strokes it joins. See `best_pair`.
    """
    n = len(contours)
    pairs = {}
    for i in range(n):
        for j in range(i + 1, n):
            if collinearity_weight > 0:
                pi, pj, d, c = best_pair(contours[i], contours[j], collinearity_weight)
            else:
                pi, pj, d = closest_pair(contours[i], contours[j])
                c = d
            pairs[(i, j)] = (pi, pj, d, c)
    joined, edges = {0}, []
    while len(joined) < n:
        best = None
        for i in joined:
            for j in range(n):
                if j in joined:
                    continue
                pi, pj, d, c = pairs[(min(i, j), max(i, j))]
                if min(i, j) != i:
                    pi, pj = pj, pi
                if best is None or c < best[5]:
                    best = (i, j, d, pi, pj, c)
        edges.append(best[:5])
        joined.add(best[1])
    return edges


def merge(contours: list[np.ndarray], collinearity_weight: float = 0.0
          ) -> tuple[np.ndarray, float, list]:
    """
    Return (single closed curve, total connector length, the connector tree).

    The curve visits every point of every contour exactly once and every
    connector exactly twice, so its length is
    `sum(contour perimeters) + 2 * connector length`.
    """
    edges = connector_tree(contours, collinearity_weight)
    children: dict[int, list] = {i: [] for i in range(len(contours))}
    for i, j, d, pi, pj in edges:
        children[i].append((j, pi, pj))

    def walk(i: int, entry: int) -> list[np.ndarray]:
        contour = contours[i]
        pts: list[np.ndarray] = []
        for idx in np.roll(np.arange(len(contour)), -entry):
            pts.append(contour[idx])
            for j, pi, pj in children[i]:
                if pi == idx:
                    pts.extend(walk(j, pj))      # out along the connector,
                    pts.append(contour[idx])     # round the child, and back
        pts.append(contour[(entry) % len(contour)])
        return pts

    return np.array(walk(0, 0)), sum(e[2] for e in edges), edges


def text_contours(text: str, size: float = 1.0, family: str = "DejaVu Sans") -> list[np.ndarray]:
    """A word's letterform outlines, as closed contours. Counters come out too."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath

    path = TextPath((0, 0), text, size=size, prop=FontProperties(family=family))
    out = []
    for poly in path.to_polygons(closed_only=True):
        p = np.asarray(poly, dtype=float)
        if len(p) > 2 and np.allclose(p[0], p[-1]):
            p = p[:-1]
        if len(p) > 2:
            out.append(p)
    return out


# How hard to push connectors away from looking like strokes, per style. An
# outline needs none: a bridge between two closed letterforms reads as a bridge.
# A single-stroke drawing is all thin lines, so the connector has to be told to
# meet the strokes at an angle. POC 12 swept this - see poc12_connector_sweep.
COLLINEARITY_WEIGHT = {"outline": 0.0, "stroke": 6.0}


def text_curve(text: str, style: str = "outline", step: float = 0.01,
               family: str = "DejaVu Sans",
               collinearity_weight: float | None = None) -> np.ndarray:
    """
    A word as one closed curve, normalised to width 1 and centred.

    `style="outline"` traces both edges of every letter stroke - the letter as
    printed. `style="stroke"` uses the single-stroke font: one line down the
    middle of each stroke, ridden out and back. Outline is the better-looking
    of the two and costs more distance; the choice belongs to the rider, so it
    is a parameter rather than a default.
    """
    if style == "outline":
        contours = [densify(p, step) for p in text_contours(text, family=family)]
    elif style == "stroke":
        from stroke_font import stroke_to_contour, strokes
        contours = [densify(stroke_to_contour(s), step) for s in strokes(text)]
    else:
        raise ValueError(f"unknown style {style!r}; use 'outline' or 'stroke'")
    if collinearity_weight is None:
        collinearity_weight = COLLINEARITY_WEIGHT[style]
    curve, _, _ = merge(contours, collinearity_weight)
    span = curve.max(axis=0) - curve.min(axis=0)
    return (curve - curve.min(axis=0) - span / 2) / span[0]
