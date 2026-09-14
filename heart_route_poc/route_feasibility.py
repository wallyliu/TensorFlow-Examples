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

import math

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

# ...and it is not a constant. POC 25 measured the detour of the route the
# pipeline actually keeps, over two shapes and four sizes, and added the large
# fits from POC 21, 23 and 24:
#
#     2.5 km 1.29   4.2 km 1.21   5.0 km 1.32   7.3 km 1.54   8.7 km 1.92
#    12.3 km 1.93   12.3 km 2.18  12.4 km 1.75  12.4 km 1.82
#
# A straight line in width fits with a residual sd of 0.159 and no residual
# worse than 0.250. Against those same nine, the constant 1.25 has a residual sd
# of 0.339 and a MEAN error of +0.412 - it does not merely scatter, it
# understates, and it understates the thing the product promises a rider. The
# 50 km heart was quoted 42.5-57.5 km and measured 72.2.
#
# Deliberately a straight line and nothing richer: nine points over two shapes
# cannot support more parameters, and the quantity being replaced had one.
# POC 24 ruled out the obvious confound - this is not placement scarcity, since
# letting the search choose from twenty placements instead of one moves the
# detour by 0.14 at 2.5 km and by nothing at 12.4 km.
# ...and it is not only a function of size either. POC 26 fitted the same
# 10 km heart in seven cities and Keelung came out at 1.82 where the
# Taipei-fitted line predicts 1.22 - the single worst residual, 0.508. Adding
# the city's own street scale as a second predictor over all sixteen fits cuts
# the residual sd from 0.193 to 0.173 and the worst residual to 0.269.
#
# The coefficient below is expressed per metre of LOCAL street_scale rather
# than per metre of the directional measurement it was fitted on, so that
# callers pass the same quantity they size with; the two differ by Taipei's
# 142/280, which is folded in. At Taipei's 280 m the pair reproduce the
# width-only Taipei fit to three decimals (1.036 against 1.024), which is the
# check that the second term is describing other cities and not quietly
# re-describing Taipei.
DETOUR_INTERCEPT = 0.4544
DETOUR_PER_KM = 0.0734
DETOUR_PER_SCALE_M = 0.002079
DETOUR_RESIDUAL_SD = 0.173

# Per-mode constants. Bicycle is the default: it is the mode the product is for,
# and the walking numbers are kept because nine POCs of measurement rest on them.
MODES = {
    "walk": {"street_scale_m": 160.0, "detour": 1.25, "label": "walking"},
    "bike": {"street_scale_m": 280.0, "detour": 1.26, "label": "cycling"},
}
DEFAULT_MODE = "bike"


def detour_for(width_m: float, street_scale_m: float | None = None,
               mode: str = DEFAULT_MODE) -> float:
    """The detour a shape this wide pays on streets this far apart."""
    scale = street_scale_m or MODES[mode]["street_scale_m"]
    return (DETOUR_INTERCEPT + DETOUR_PER_KM * (width_m / 1000.0)
            + DETOUR_PER_SCALE_M * scale)


def width_for(shape: str, target_km: float,
              street_scale_m: float | None = None,
              mode: str = DEFAULT_MODE) -> float:
    """
    How wide to draw a shape so the ride comes out at target_km.

    Not a division any more. The route is perimeter x width x detour, and the
    detour is itself a function of width, so the two have to be solved together:
    P.b.w^2 + P.a.w - T = 0 with w in km. Dividing by a fixed detour is what
    made a 50 km request come back 22 km long.
    """
    per = perimeter(shape)
    scale = street_scale_m or MODES[mode]["street_scale_m"]
    a = DETOUR_INTERCEPT + DETOUR_PER_SCALE_M * scale
    b = DETOUR_PER_KM
    w_km = (-per * a + math.sqrt((per * a) ** 2 + 4 * per * b * target_km)) / (2 * per * b)
    return w_km * 1000.0

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


SMOOTHING_WINDOW = 5       # grid steps, so 5 covers 20 contour points


@lru_cache(maxsize=None)
def n_min(shape: str, tolerance: float = SAMPLING_TOLERANCE, ceiling: int = 400) -> int:
    """
    The fewest contour points that represent this shape well enough.

    The loss curve has two kinds of noise on it and the rule has to survive
    both. A polygon sampled at a multiple of its vertex count is reproduced
    exactly, so the curve dips to zero and back - taking the first crossing
    would read one of those lucky alignments as convergence. And a shape with
    repeated fine structure makes the curve RING: Taipei 101's sixteen module
    steps beat against the sample count, so the loss crosses the tolerance at
    176 points and then pops back over it at 200, 208, 280 and 316.

    The previous rule - below tolerance for ALL larger n - handled the dips and
    was defeated by the ringing, reading 101's last crossing and returning 320
    against a true cost near 176. Nearly double, on any shape with a repeated
    feature: a gear, a comb, a skyline.

    Both are sampling artefacts rather than properties of the shape, and a
    rolling median over the grid removes both: it ignores a single lucky dip
    and a single unlucky beat alike, while leaving the underlying decay alone.
    The rule then applies to the smoothed curve.
    """
    grid = list(range(4, ceiling + 1, 4))
    raw = [sampling_loss(shape, n) for n in grid]
    half = SMOOTHING_WINDOW // 2
    smooth = [float(np.median(raw[max(0, i - half):i + half + 1]))
              for i in range(len(grid))]
    for i, n in enumerate(grid):
        if all(value < tolerance for value in smooth[i:]):
            return n
    return ceiling


def min_distance_km(shape: str, mode: str = DEFAULT_MODE,
                    street_scale_m: float | None = None) -> float:
    """The shortest route this shape can produce in this mode and still be itself.

    `street_scale_m` overrides the national constant for one place. POC 26
    found the constant is not national: Keelung's streets are 223 m apart in a
    given direction against Taipei's 142 m, and asking it for 280 m anchors
    produced a 15.0 km route for a 10 km request at a shape distance of 0.266.
    A sparse city needs a physically bigger shape to draw the same figure, and
    that is what a larger scale here says.
    """
    cfg = MODES[mode]
    scale = street_scale_m or cfg["street_scale_m"]
    width = n_min(shape) * scale / perimeter(shape)
    return perimeter(shape) * width * detour_for(width, scale, mode) / 1000.0


# Where inside the window to sit. POC 9 swept this across five shapes, found the
# optimum at 0.50, 0.69, 0.75, 0.83 and 1.00 of the cap, and concluded that the
# position was unpredictable but immaterial - the whole sweep spanned only
# 0.013-0.041 in shape distance, well under the ~0.10 at which a person sees a
# difference. 0.75 was the measured mean.
#
# "Immaterial" was too strong, and the triangle is the counter-example. At 8 km
# the 0.75 fraction gives it 16 anchors, 687 m apart against a 280 m street
# scale, and between anchors that far apart the route is barely constrained:
# it scored 0.127, which is ABOVE the threshold, and a user said so before any
# measurement did. Refitting the same placement at 24 and 32 anchors gives
# 0.094 and 0.095. The span is indeed ~0.03 - but it straddles the threshold,
# so where in the window you sit decides whether the shape reads or not.
#
# 1.0 puts anchors one street scale apart, which is what the cap means. Checked
# not to cost anything on the shape it was not chosen for: the heart at 10 km
# runs 0.079 / 0.079 / 0.077 / 0.085 across 21, 28, 36 and 48 anchors.
WINDOW_FRACTION = 1.0


def contour_points(shape: str, width_m: float, mode: str = DEFAULT_MODE,
                   street_scale_m: float | None = None) -> int:
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
    scale = street_scale_m or MODES[mode]["street_scale_m"]
    cap = max(1, int(perimeter(shape) * width_m / scale))
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


def plan(shape: str, target_km: float, mode: str = DEFAULT_MODE,
         street_scale_m: float | None = None) -> Plan:
    """
    Size a shape to a distance, or explain why it does not fit.

    A refusal carries the number the asker needs ("a dinosaur needs 19.1 km"),
    never a bare "not available" - and never a silently degraded shape, which is
    the failure this whole project keeps running into: the metric cannot see a
    destroyed feature, so the check has to happen HERE, before anything is drawn.
    """
    floor = min_distance_km(shape, mode, street_scale_m)
    if target_km < floor:
        return Plan(shape, mode, False, target_km, floor, None, None, None, None,
                    f"needs at least {floor:.1f} km; too much detail to fit in "
                    f"{target_km:.1f} km of {MODES[mode]['label']}")

    width = width_for(shape, target_km, street_scale_m, mode)
    points = contour_points(shape, width, mode, street_scale_m)
    detour = detour_for(width, street_scale_m, mode)
    predicted = perimeter(shape) * width * detour / 1000.0
    # The band comes from the fit's own residual scatter rather than a flat
    # percentage. +-2 sd covers every one of the nine measured fits; a flat
    # +-15% did not, and was widest exactly where the estimate was best.
    slack = perimeter(shape) * width * 2 * DETOUR_RESIDUAL_SD / 1000.0
    span = (max(0.0, predicted - slack), predicted + slack)
    return Plan(shape, mode, True, target_km, floor, width, points, predicted, span,
                f"{width / 1000:.1f} km wide, {points} contour points")


def feasible_shapes(target_km: float, mode: str = DEFAULT_MODE) -> list[Plan]:
    """Every shape sized to this distance, feasible ones first, then by floor."""
    plans = [plan(s, target_km, mode) for s in SHAPES]
    return sorted(plans, key=lambda p: (not p.feasible, p.min_km))
