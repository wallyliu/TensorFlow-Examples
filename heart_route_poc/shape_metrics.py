"""
POC 4 - candidate shape metrics
===============================

POC 3 caught the search gaming its own objective: a heart tilted 30 degrees
scored identically to an upright one and looked far worse. The diagnosis there
blamed the metric. Reading the code, the real culprit is narrower and more
embarrassing: chamfer was computed against the PLACED AND ROTATED reference
contour. Rotate the target with the candidate and no comparison function on
earth can see the rotation. The reference was wrong, not the arithmetic.

That suggests the fix might be far cheaper than a new metric - compare against a
canonical UPRIGHT template instead - so this module implements four candidates
and lets the diagnostics decide:

    chamfer_placed     the incumbent: chamfer vs the placed, rotated reference
    chamfer_upright    chamfer vs an upright template, after normalising away
                       translation and scale (but NOT rotation)
    procrustes_upright ordered point-to-point distance against the same upright
                       template, minimised over cyclic shift and direction only
    turning_upright    turning-function distance, in its rotation-SENSITIVE form

The last one needs a warning. POC 3 recommended a turning function on the
grounds that it "is not invariant to the tilt that fooled this POC". That is
wrong as usually defined: the classic Arkin turning-function distance minimises
over the angular offset and is therefore rotation-invariant BY DESIGN. Getting
tilt sensitivity from it means deliberately not doing that minimisation, which
is what `rotation_invariant=False` means below.

Everything here is scale- and translation-invariant, because where a heart is
and how big it is have nothing to do with whether it looks like a heart. None
of it is rotation-invariant unless asked, because tilt very much does.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

RESAMPLE_N = 256


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def resample_closed(xy: np.ndarray, n: int = RESAMPLE_N) -> np.ndarray:
    """Resample a closed curve at `n` equally spaced points by arc length."""
    pts = np.asarray(xy, dtype=float)
    if not np.allclose(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[:1]])

    seg = np.hypot(*np.diff(pts, axis=0).T)
    cumulative = np.concatenate([[0.0], np.cumsum(seg)])
    total = cumulative[-1]
    if total <= 0:
        msg = "degenerate curve: zero length"
        raise ValueError(msg)

    targets = np.linspace(0.0, total, n, endpoint=False)
    return np.column_stack([
        np.interp(targets, cumulative, pts[:, 0]),
        np.interp(targets, cumulative, pts[:, 1]),
    ])


def normalize_curve(xy: np.ndarray, n: int = RESAMPLE_N) -> np.ndarray:
    """
    Centre on the centroid and divide by RMS radius - removing translation and
    scale, and nothing else.

    Deliberately NOT removing rotation: that is the whole point. RMS radius is
    used rather than bounding-box width because a single spur sticking out of
    the route can move a bounding box several percent, while it barely moves an
    average taken over 256 points.
    """
    pts = resample_closed(xy, n)
    pts = pts - pts.mean(axis=0)
    scale = float(np.sqrt((pts ** 2).sum(axis=1).mean()))
    return pts / scale


# ---------------------------------------------------------------------------
# Metric 1 / 2 - chamfer, against either reference
# ---------------------------------------------------------------------------
def chamfer(a: np.ndarray, b: np.ndarray) -> float:
    """Symmetric mean nearest-neighbour distance, in whatever units come in."""
    to_b = cKDTree(b).query(a)[0]
    to_a = cKDTree(a).query(b)[0]
    return float((to_b.mean() + to_a.mean()) / 2.0)


def chamfer_placed(route_xy: np.ndarray, reference_xy: np.ndarray) -> float:
    """The incumbent metric from POC 1-3, in metres. Blind to rotation."""
    return chamfer(resample_closed(route_xy, 1024), resample_closed(reference_xy, 1024))


def chamfer_upright(route_xy: np.ndarray, template_xy: np.ndarray,
                    n: int = 2048) -> float:
    """
    Chamfer after normalising translation and scale away, against an upright
    template. Same arithmetic as the incumbent, different reference.

    Resampled far more finely than the ordered metrics because a k-d tree query
    is cheap and the residual from comparing two point sets sampled at different
    phase is half the sample spacing - which at n=256 is large enough to swamp
    the invariance checks.
    """
    return chamfer(normalize_curve(route_xy, n), normalize_curve(template_xy, n))


# ---------------------------------------------------------------------------
# Metric 3 - ordered point distance
# ---------------------------------------------------------------------------
def procrustes_upright(
    route_xy: np.ndarray,
    template_xy: np.ndarray,
    n: int = 1024,
    allow_rotation: bool = False,
) -> float:
    """
    Mean distance between corresponding points of two normalised curves,
    minimised over the two things that genuinely do not matter:

      * where you started walking the loop (cyclic shift), and
      * which way round you walked it (direction).

    and NOT over rotation, unless `allow_rotation` is set - which exists only so
    the diagnostics can show what that one change costs.

    Unlike chamfer this is an ORDERED comparison: it notices a route that visits
    the right places in the wrong sequence, which a nearest-neighbour distance
    cannot see at all.
    """
    a = normalize_curve(route_xy, n)
    b = normalize_curve(template_xy, n)
    a_complex = a[:, 0] + 1j * a[:, 1]

    best = np.inf
    for flipped in (False, True):
        b_dir = b[::-1] if flipped else b
        b_complex = b_dir[:, 0] + 1j * b_dir[:, 1]
        for shift in range(n):
            candidate = np.roll(b_complex, shift)
            if allow_rotation:
                # Optimal rotation for a fixed correspondence, in closed form.
                overlap = np.vdot(candidate, a_complex)
                if overlap != 0:
                    candidate = candidate * (overlap / abs(overlap))
            best = min(best, float(np.abs(a_complex - candidate).mean()))
    return best


def sampling_floor(xy: np.ndarray, n: int) -> float:
    """
    The residual a phase-shifted comparison cannot get below at this resolution.

    Two identical curves sampled from different starting points land half a
    sample spacing apart on average, so any invariance check has to be read
    against this number rather than against zero.
    """
    normalised = normalize_curve(xy, n)
    perimeter = np.hypot(*np.diff(np.vstack([normalised, normalised[:1]]), axis=0).T).sum()
    return float(perimeter / (2 * n))


# ---------------------------------------------------------------------------
# Metric 4 - turning function
# ---------------------------------------------------------------------------
def turning_function(xy: np.ndarray, n: int = RESAMPLE_N) -> np.ndarray:
    """
    Cumulative tangent direction as a function of arc length.

    Each step's turn is wrapped into [-pi, pi] before accumulating, so the
    result winds by exactly +-2*pi over a simple closed loop rather than
    jumping at the atan2 branch cut.
    """
    pts = resample_closed(xy, n)
    deltas = np.diff(np.vstack([pts, pts[:1]]), axis=0)
    angles = np.arctan2(deltas[:, 1], deltas[:, 0])

    steps = np.diff(angles, prepend=angles[0])
    steps = (steps + np.pi) % (2 * np.pi) - np.pi
    return angles[0] + np.cumsum(steps)


def winding(xy: np.ndarray, n: int = RESAMPLE_N) -> float:
    """
    Total turning over the closed curve, which for ANY simple closed curve must
    be exactly +-2*pi.

    This is the turning function's own self-test, and the heart fails it: see
    the POC 4 write-up. At a cusp the tangent reverses by exactly pi and the
    sign of that turn is genuinely ambiguous, so the accumulation picks a branch
    and the error never washes out - it grows with resolution instead of
    shrinking. Any turning-function distance on a cusped shape inherits that.
    """
    theta = turning_function(xy, n)
    return float(theta[-1] - theta[0])


def turning_upright(
    route_xy: np.ndarray,
    template_xy: np.ndarray,
    n: int = RESAMPLE_N,
    rotation_invariant: bool = False,
) -> float:
    """
    RMS difference between two turning functions, in radians.

    Minimised over cyclic shift. The constant angular offset is handled
    differently depending on what we want to measure:

      rotation_invariant=True   subtract the mean offset - the classic Arkin
                                distance, which cannot see tilt.
      rotation_invariant=False  subtract only the nearest whole turn, which
                                cancels the bookkeeping from starting the loop
                                at a different point while leaving genuine
                                rotation in place.
    """
    theta_a = turning_function(route_xy, n)
    theta_b = turning_function(template_xy, n)
    # Extend by one full winding so a cyclic shift reads off a continuous run.
    winding = theta_b[-1] - theta_b[0]
    extended = np.concatenate([theta_b, theta_b + winding])

    best = np.inf
    for shift in range(n):
        shifted = extended[shift:shift + n]
        difference = theta_a - shifted
        if rotation_invariant:
            offset = difference.mean()
        else:
            offset = 2 * np.pi * np.round(difference.mean() / (2 * np.pi))
        best = min(best, float(np.sqrt(((difference - offset) ** 2).mean())))
    return best
