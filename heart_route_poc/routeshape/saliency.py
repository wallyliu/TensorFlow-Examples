"""
Which parts of an outline the route must hit, and which it may let go.

The matcher trades snap error against detour with one global weight. That
spends the same effort holding a cup's handle and holding the flat side of the
cup, and the handle is the entire reason anybody can name it. POC 34 measured
where a shape's identity actually lives; this turns that into the per-point
weights `matching.viterbi_closed_loop` now accepts.

TWO WAYS TO MEASURE IT AND ONLY ONE WORKS. Flatten one arc of the outline -
replace it with the straight chord across it - and ask what that costs:

  self            how much shape_distance to the shape's own template rises.
                  This is curvature in disguise, and curvature is not identity:
                  the crown is all corners and three raters named it 0/6.
  discriminative  how much CLOSER the flattened shape moves to its nearest
                  other shape in the library. This asks what stops it being
                  something else, which is the rule POC 32 produced from the
                  rater data and the one that keeps being right.

The discriminative map finds the parts unaided - the cup's handle root, the
plane's wingtips, the gear's centre bore, the crown's deep valleys rather than
the flat base it shares with every trapezoid.

WEIGHTS ARE NORMALISED TO MEAN 1, so the balance between snapping and detouring
is unchanged overall and only its DISTRIBUTION moves. CONTRAST sets how far:
4.0 means the most identity-bearing arc is pulled four times as hard as the
least. Nothing about that number is measured yet.

This cannot be validated against `shape_distance`. Holding the important arcs
tighter costs error elsewhere, so a weighted route scores WORSE on the
unweighted metric while being the one a person can name - which is exactly the
gap POC 36 measured at p = 0.016. It ships only behind a rater round.
"""

from __future__ import annotations

import numpy as np

from routeshape.metrics import shape_distance
from routeshape.shapes.library import SHAPES, resample_by_arclength

RESAMPLE = 256
REGIONS = 32
CONTRAST = 4.0
_CACHE: dict = {}


def _flattened(curve: np.ndarray, region: int, span: int) -> np.ndarray:
    """The curve with one arc replaced by the straight chord across it."""
    out = curve.copy()
    idx = [(region * span + k) % len(curve) for k in range(span + 1)]
    start, end = out[idx[0]], out[idx[-1]]
    for k, j in enumerate(idx):
        out[j] = start + (end - start) * (k / (len(idx) - 1))
    return out


def discriminative(shape: str, regions: int = REGIONS) -> np.ndarray:
    """Per-region: how much flattening it moves the shape toward another one."""
    key = (shape, regions, len(SHAPES))
    if key in _CACHE:
        return _CACHE[key]
    base = resample_by_arclength(shape, RESAMPLE)
    others = [resample_by_arclength(name, RESAMPLE)
              for name in SHAPES if name != shape]
    if not others:
        return np.ones(regions)
    nearest = min(shape_distance(base, other) for other in others)
    span = RESAMPLE // regions
    moved = np.array([
        max(0.0, nearest - min(shape_distance(_flattened(base, r, span), other)
                               for other in others))
        for r in range(regions)])
    _CACHE[key] = moved
    return moved


def weights(shape: str, points: int, contrast: float = CONTRAST,
            regions: int = REGIONS) -> np.ndarray:
    """One snap weight per contour point, mean 1.

    The contour points the matcher uses are equally spaced by arc length and so
    are the regions, so a point's weight is its region's, read off by position.
    """
    moved = discriminative(shape, regions)
    spread = float(moved.max() - moved.min())
    if spread <= 0:
        return np.ones(points)
    normalised = (moved - moved.min()) / spread          # 0 .. 1
    per_region = contrast ** (normalised - 0.5)          # 1/sqrt(c) .. sqrt(c)
    at = (np.arange(points) * regions) // points
    per_point = per_region[at]
    return per_point / float(per_point.mean())


BASE_RADIUS_M = 300.0
TIGHT_M, LOOSE_M = 110.0, 650.0


def radii(point_weights: np.ndarray, base: float = BASE_RADIUS_M,
          tight: float = TIGHT_M, loose: float = LOOSE_M) -> np.ndarray:
    """How far each contour point may be snapped, from its weight.

    Weighting the emission cost alone moved almost nothing - two of five shapes
    came out byte-identical - because the DP had two blocks of freedom and no
    room to trade. The radius is where the freedom lives, so it is what the
    weights should move: an identity-bearing arc gets a tight one and has to
    land close, a filler arc gets a loose one and may take whatever street is
    convenient.

    ONLY THE TIGHT END IS A LEVER, and the defaults barely touch it. The
    candidate set is the k nearest junctions WITHIN the radius, so widening it
    past the k-th nearest one changes nothing: at k = 18 the loose end is
    inert. POC 38 measured the result - `radius` came out byte-identical to a
    flat 260 m on the cup and within 0.001 on the gear, with candidate counts
    of 17.8 out of 18. `tight` and `loose` are parameters so a sweep can push
    the end that does something.
    """
    return np.clip(base / np.asarray(point_weights, dtype=float), tight, loose)
