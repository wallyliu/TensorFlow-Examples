"""
Can this shape be walked in the distance someone asked for?

POC 8 established that shape complexity sets a floor on walking distance, and
the derivation collapses to something small enough to put in a UI:

    W_min = n_min x s / P          the smallest width whose n-window is non-empty
    D     = P x W x detour         the walk a shape of width W produces
    D_min = P x W_min x detour = n_min x s x detour

The perimeter cancels. A shape's minimum walkable distance depends only on how
many contour points it needs, the street grid's characteristic scale, and the
detour the network imposes - not on how long its outline is.

That leaves ONE integer per shape (`n_min`, computed offline in milliseconds
with no map) and ONE number per city (`s`). Everything a product needs to say
"a dinosaur needs 19 km, and you asked for 5" follows from those.

The direction that matters for a UI is the reverse one: given a distance, solve
for the width, and check it clears the floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from shape_library import SHAPES, resample_by_arclength
from shape_metrics import shape_distance

# The spacing at which contour sampling stops helping and starts over-constraining
# the matcher. A property of the city AND the mode - a cyclist may not use the
# pavements and alleys that make a walking network dense.
#
# Honest about where these come from. The walking 160 m is POC 7's, taken as the
# argmin of a resolution sweep - and POC 10 found that sweep is flat within the
# perceptual threshold, so the argmin is largely noise and 160 m is an empirical
# fitting constant, not a measured quantity. The bicycle value is NOT measured
# independently either: it is 160 m scaled by 1.75, the measured ratio of median
# junction spacing along real routes (23 m walking, 40 m cycling), which is a
# robust network statistic even though it is not the same quantity.
#
# That transfer earns its keep by making out-of-sample predictions. It says the
# star and the T-rex cannot clear the perceptual threshold as 2 km cycling
# routes and the other three can - and all five came out that way when measured.
TAIPEI_STREET_SCALE_M = 160.0

# Measured over 12 fits spanning five shapes and three sizes (POC 9): mean
# 1.252, sd 0.068, range 1.14-1.35. It is NOT the constant the earlier POCs
# assumed - it varies by shape (star 1.19, heart 1.29) and rises with size
# (1.19 at a 5 km target, 1.28 at 20 km), though the size trend is partly
# confounded, since a shape 5 km wide has far fewer placements to choose from
# inside a 9 km network than a 1 km one does.
#
# A single number therefore carries about +-10% of residual error, which is why
# `Plan` reports a RANGE. Promising "10.0 km" and delivering 8.8 km is the kind
# of quiet lie this project keeps finding in its own metrics.
DETOUR_RATIO = 1.25
DETOUR_UNCERTAINTY = 0.15   # +-10% covered 10 of 12 measured fits; +-15% covered all 12

# Per-mode constants. Bicycle is the default: it is the mode the product is for,
# and the walking numbers are kept because nine POCs of measurement rest on them.
MODES = {
    "walk": {"street_scale_m": 160.0, "detour": 1.25, "label": "walking"},
    "bike": {"street_scale_m": 280.0, "detour": 1.26, "label": "cycling"},
}
DEFAULT_MODE = "bike"

# Sampling loss must stay well under the ~0.10 gap at which a person reliably
# sees a difference (POC 6), so that sampling is not itself eating the budget.
SAMPLING_TOLERANCE = 0.05

DENSE = 4000


@lru_cache(maxsize=None)
def perimeter(shape: str) -> float:
    """Contour length of the normalised shape, in units of its own width."""
    pts = resample_by_arclength(shape, DENSE)
    closed = np.vstack([pts, pts[:1]])
    return float(np.hypot(*np.diff(closed, axis=0).T).sum())


@lru_cache(maxsize=None)
def sampling_loss(shape: str, n: int) -> float:
    """How much of the shape an n-point polygon throws away. No map involved."""
    return shape_distance(resample_by_arclength(shape, n), resample_by_arclength(shape, DENSE))


@lru_cache(maxsize=None)
def n_min(shape: str, tolerance: float = SAMPLING_TOLERANCE, ceiling: int = 400) -> int:
    """
    The fewest contour points that represent this shape well enough.

    Defined as the smallest n from which the loss stays below tolerance for ALL
    larger n, not merely the first n that dips under it. The distinction is not
    pedantic: a polygon shape sampled at a multiple of its vertex count is
    reproduced exactly, so the loss curve dips to zero and back up again, and
    "first crossing" would pick up one of those lucky alignments.
    """
    grid = list(range(4, ceiling + 1, 4))
    losses = {n: sampling_loss(shape, n) for n in grid}
    for n in grid:
        if all(losses[m] < tolerance for m in grid if m >= n):
            return n
    return ceiling


def min_distance_km(shape: str, mode: str = DEFAULT_MODE) -> float:
    """The shortest route this shape can produce in this mode and still be itself."""
    cfg = MODES[mode]
    return n_min(shape) * cfg["street_scale_m"] * cfg["detour"] / 1000.0


# Where inside the window to sit. POC 9 swept this across five shapes and found
# the optimum at 0.50, 0.69, 0.75, 0.83 and 1.00 of the cap - so no single
# fraction is right. It also found the whole sweep spans only 0.013-0.041 in
# shape distance for every shape, far below the ~0.10 at which a person sees a
# difference. The position is unpredictable AND immaterial: any n in the window
# gives a perceptually identical route. 0.75 is the measured mean.
WINDOW_FRACTION = 0.75


def contour_points(shape: str, width_m: float, mode: str = DEFAULT_MODE) -> int:
    """
    How many contour points to sample, for a shape drawn this wide.

    The window runs from n_min (enough to represent the shape) to one point per
    street scale (beyond which extra points are constraints the grid cannot
    satisfy). Sitting slightly below the cap rather than at n_min matters for
    large shapes: a heart 4.8 km wide sampled at its n_min of 12 puts anchors
    1.3 km apart, and the route between two anchors that far apart is barely
    constrained at all - the sampled polygon is heart-shaped while the walk need
    not be.
    """
    cap = max(1, int(perimeter(shape) * width_m / MODES[mode]["street_scale_m"]))
    return max(n_min(shape), round(WINDOW_FRACTION * cap))


@dataclass(frozen=True)
class Plan:
    """What a given distance buys for a given shape."""
    shape: str
    mode: str
    feasible: bool
    target_km: float
    min_km: float
    width_m: float | None          # how wide to draw it, None when infeasible
    points: int | None             # contour points to sample, None when infeasible
    predicted_km: float | None
    range_km: tuple[float, float] | None   # what the route will plausibly measure
    reason: str


def plan(shape: str, target_km: float, mode: str = DEFAULT_MODE) -> Plan:
    """
    Size a shape to a distance, or explain why it does not fit.

    A refusal carries the number the asker needs ("a dinosaur needs 19.1 km"),
    never a bare "not available" - and never a silently degraded shape, which is
    the failure this whole project keeps running into: the metric cannot see a
    destroyed feature, so the check has to happen HERE, before anything is drawn.
    """
    detour = MODES[mode]["detour"]
    floor = min_distance_km(shape, mode)
    if target_km < floor:
        return Plan(shape, mode, False, target_km, floor, None, None, None, None,
                    f"needs at least {floor:.1f} km; too much detail to fit in "
                    f"{target_km:.1f} km of walking")

    width = target_km * 1000.0 / (perimeter(shape) * detour)
    points = contour_points(shape, width, mode)
    predicted = perimeter(shape) * width * detour / 1000.0
    span = (predicted * (1 - DETOUR_UNCERTAINTY), predicted * (1 + DETOUR_UNCERTAINTY))
    return Plan(shape, mode, True, target_km, floor, width, points, predicted, span,
                f"{width / 1000:.1f} km wide, {points} contour points")


def feasible_shapes(target_km: float, mode: str = DEFAULT_MODE) -> list[Plan]:
    """Every shape sized to this distance, feasible ones first, then by floor."""
    plans = [plan(s, target_km, mode) for s in SHAPES]
    return sorted(plans, key=lambda p: (not p.feasible, p.min_km))
