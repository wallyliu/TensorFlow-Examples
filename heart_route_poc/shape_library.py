"""
Target shapes for the route generator.

POC 1-5 hard-coded one parametric heart. POC 6 asks whether the pipeline is a
heart trick or a shape pipeline, which needs shapes that stress it differently:

    heart      two cusps, one shallow concavity - the known baseline
    trex       many concave features at very different scales, and an eye that
               cannot be represented at all
    star5      five sharp points and five DEEP concavities, plus 72-degree
               rotational symmetry
    crescent   one deep concavity and two very sharp cusps, strongly asymmetric
    triangle   convex, three corners, no concavity at all - the easy control

The control matters. Without a shape the street grid should handle easily,
a bad star score cannot be told apart from a bad pipeline.

Every generator returns `n` ordered points, closed implicitly (last point does
not repeat the first), centred on the bounding box and scaled so WIDTH is
exactly 1.0 - the same convention `generate_heart_points` established, so the
placement code needs no changes.
"""

from __future__ import annotations

import numpy as np

from heart_route_poc import generate_heart_points


def _normalise(points: np.ndarray) -> np.ndarray:
    """Centre on the bounding box and divide both axes by the width.

    Dividing both axes by the same number preserves the aspect ratio, so a
    shape's own proportions survive; only `width_m` at placement time sets scale.
    """
    x, y = points[:, 0], points[:, 1]
    centred = np.column_stack([x - (x.max() + x.min()) / 2, y - (y.max() + y.min()) / 2])
    return centred / (x.max() - x.min())


def _resample_polygon(vertices: np.ndarray, n: int) -> np.ndarray:
    """Spread `n` points evenly by arc length around a closed polygon.

    Corners land wherever the spacing puts them rather than being forced into
    the sample set. That is deliberate: the router only ever sees sampled
    points, so a corner it cannot see is a corner it cannot chase, and
    pretending otherwise would flatter the result.
    """
    closed = np.vstack([vertices, vertices[:1]])
    seg = np.hypot(*np.diff(closed, axis=0).T)
    cumulative = np.concatenate([[0.0], np.cumsum(seg)])
    targets = np.linspace(0.0, cumulative[-1], n, endpoint=False)
    return np.column_stack([
        np.interp(targets, cumulative, closed[:, 0]),
        np.interp(targets, cumulative, closed[:, 1]),
    ])


def heart(n: int = 40) -> np.ndarray:
    """The POC 1-5 baseline, unchanged."""
    return generate_heart_points(n)


def star5(n: int = 40, inner_ratio: float = 0.382) -> np.ndarray:
    """
    A five-pointed star, point upward.

    `inner_ratio` 0.382 is the classic pentagram proportion (1/phi^2). It also
    makes this the hardest shape here: the contour has to reverse direction ten
    times, and the concave notches run deep into the middle, where a street grid
    has nothing to offer.
    """
    angles = np.pi / 2 + np.arange(10) * (np.pi / 5)
    radii = np.where(np.arange(10) % 2 == 0, 1.0, inner_ratio)
    vertices = np.column_stack([radii * np.cos(angles), radii * np.sin(angles)])
    return _normalise(_resample_polygon(vertices, n))


def crescent(n: int = 40, inner_radius: float = 0.86, offset: float = 0.34) -> np.ndarray:
    """
    A crescent moon: a disc with a second disc bitten out of it.

    Built with shapely rather than by hand because the boundary is two circular
    arcs meeting at two cusps, and solving for the intersections directly is
    fiddly and easy to get subtly wrong.
    """
    from shapely.geometry import Point

    outer = Point(0.0, 0.0).buffer(1.0, quad_segs=512)
    inner = Point(offset, 0.0).buffer(inner_radius, quad_segs=512)
    boundary = np.asarray(outer.difference(inner).exterior.coords)[:-1]
    return _normalise(_resample_polygon(boundary, n))


# The outline of Chrome's offline dinosaur, traced from the sprite rather than
# drawn by hand: the dark pixels were thresholded, the largest connected
# component taken (dropping the cactus and the ground dashes), holes filled, and
# the 0.5 contour of that mask simplified to 58 vertices - which changes its
# enclosed area by 0.19%, so the silhouette is the sprite's, not an impression
# of it.
#
# Filling the holes removed exactly one: a 13x12 px eye, 0.85% of the dinosaur's
# area and 6.4% of its width. At a 2 km target that eye would be 128 m across,
# comfortably above the ~50 m this street network can resolve - so it is not too
# small to draw. It is simply not drawable: every stage here takes ONE closed
# curve, and an eye is a second one.
TREX_OUTLINE = [
    (20.5, 119.1), (93.5, 119.1), (95.0, 106.6), (107.0, 105.6), (107.0, 68.6), (57.5, 68.1),
    (57.5, 56.1), (92.5, 56.1), (94.0, 43.6), (44.0, 41.6), (45.5, 18.1), (69.0, 17.6),
    (69.0, -6.4), (57.5, -6.9), (57.0, 4.6), (45.5, 5.1), (44.0, -19.4), (32.0, -21.4),
    (31.5, -32.9), (19.0, -34.4), (19.0, -81.4), (32.0, -83.4), (32.0, -95.4), (7.5, -95.9),
    (7.0, -71.4), (-5.5, -69.9), (-6.5, -57.9), (-17.5, -57.9), (-19.0, -69.4), (-31.0, -71.4),
    (-31.0, -81.4), (-19.5, -82.9), (-18.0, -93.4), (-43.5, -94.9), (-44.0, -45.4), (-55.5, -44.9),
    (-56.5, -32.9), (-68.5, -32.9), (-69.0, -21.4), (-81.5, -19.9), (-83.5, -6.9), (-95.0, -6.4),
    (-95.0, 54.6), (-82.0, 54.6), (-82.0, 30.6), (-70.5, 30.1), (-69.5, 18.1), (-57.5, 18.1),
    (-55.5, 5.1), (-32.5, 5.1), (-31.0, 17.6), (-19.5, 18.1), (-17.5, 30.1), (-6.0, 30.6),
    (-6.0, 42.6), (7.0, 44.6), (7.0, 105.6), (18.5, 106.1),
]


def trex(n: int = 40) -> np.ndarray:
    """Chrome's dinosaur, minus its eye.

    The hardest shape in the library, and the one that shows where the pipeline
    ends. Its features span a wide range of scales - a snout, an armpit, a gap
    between two legs - so it is also the shape most sensitive to how finely the
    contour is sampled (see POC 7).
    """
    return _normalise(_resample_polygon(np.array(TREX_OUTLINE, dtype=float), n))


def triangle(n: int = 40) -> np.ndarray:
    """An equilateral triangle, point upward - convex, so the easy control."""
    angles = np.pi / 2 + np.arange(3) * (2 * np.pi / 3)
    vertices = np.column_stack([np.cos(angles), np.sin(angles)])
    return _normalise(_resample_polygon(vertices, n))


SHAPES = {"heart": heart, "star5": star5, "crescent": crescent,
          "triangle": triangle, "trex": trex}


def resample_by_arclength(shape: str, n_points: int, oversample: int = 4000) -> np.ndarray:
    """
    Sample a shape at equal arc length - POC 2's `resample_by_arclength`, but for
    any shape in the library rather than only the heart.

    Polygon shapes are already arc-length uniform, so this is a no-op for them;
    it matters for the heart, whose parametric speed varies around the curve.
    """
    dense = SHAPES[shape](oversample)
    return _resample_polygon(dense, n_points)
