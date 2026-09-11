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


# A T-rex silhouette in the spirit of Chrome's offline dinosaur, authored rather
# than traced: the point is to have a shape with MANY concave features at very
# different scales, which is what stresses the pipeline. Vertices run clockwise
# from the back of the skull, down the face and chest, around both legs, then up
# the tail and back. Coordinates are in an arbitrary 0-100 grid.
TREX_OUTLINE = [
    (58, 100), (78, 100), (78, 92), (92, 92), (92, 84),   # skull and snout
    (80, 84), (80, 78), (64, 78),                          # mouth notch and jaw
    (60, 70), (56, 60),                                    # neck into chest
    (60, 56), (70, 52), (70, 46), (58, 48),                # the little arm
    (55, 40), (54, 30),                                    # belly
    (50, 30), (50, 8), (62, 8), (62, 0), (40, 0), (40, 18),  # front leg
    (32, 18),                                              # gap between the legs
    (32, 0), (12, 0), (12, 8), (24, 8), (24, 26),          # back leg
    (16, 30), (0, 38), (0, 50), (12, 50), (12, 58),        # tail
    (26, 64), (42, 76), (52, 88),                          # back up to the skull
]


def trex(n: int = 40) -> np.ndarray:
    """A dinosaur silhouette - the hardest shape in the library.

    Note what is NOT here: the eye. The real sprite has one, and an eye is a
    HOLE. Every stage of this pipeline - the contour sampler, the placement, the
    Viterbi matcher, the metric - assumes a single closed curve, so a shape with
    a hole cannot be expressed at all, never mind drawn badly. That limit is
    topological, not a matter of resolution, and dropping the eye to get a
    runnable shape is itself the finding.
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
