"""
How likely a person is to name the shape, given how far the route came out.

POC 29, from 120 judgements by four raters on 30 real fitted routes. The
instrument is POC 28's: the route alone with no reference, named from all five
shapes at once plus "none of these", options reshuffled each trial, no feedback
and no score. Chance is 1/5.

This is NOT the 0.10 discrimination threshold, which is where a person sees
that two routes differ. It is where they stop being able to say what the route
is. The two are different numbers and the project has been careful not to
conflate them; this is the measurement that closes BACKLOG #3.

The threshold is per shape, and that is the whole point. A single threshold
fits the same 120 judgements at log-likelihood -48.1 against -33.7 for one
threshold per shape: chi2(4) = 28.7, p = 9.1e-06. The 50% points run from 0.120
for the triangle to 0.321 for the five-pointed star, a factor of 2.7. Applying
one number to all of them is the same mistake as one detour ratio for every
size and one street scale for the whole island.

Nothing predicts a shape's threshold from its geometry, so a new shape has to
be measured. Two candidates were tested and both failed: the distance to the
nearest other shape in the library (r = -0.20, Spearman p = 0.75 - and the
crescent refutes it outright, being by far the most distinctive shape at 0.513
from its nearest neighbour while having nearly the lowest threshold) and n_min
(r = -0.05). Until a shape is measured it gets the pooled threshold, which is
an average and will be wrong for anything as distinctive as a star or as
generic as a triangle.

Parallel curves - one slope shared, one threshold per shape - rather than five
free slopes, because 24 judgements per shape will not support five slopes. The
fitted slope is steep: recognition runs from near-certain to chance across
about 0.08 of shape distance.
"""

from __future__ import annotations

import math

CHANCE = 0.20
SLOPE = 52.1
# Shape distance at which half the raters still named the shape.
THRESHOLDS = {
    "triangle": 0.120,
    "crescent": 0.166,
    "trex": 0.169,
    "heart": 0.286,
    "star5": 0.321,
}
# For anything not measured - text, a new outline, a traced image.
POOLED = 0.201


def threshold(shape: str) -> float:
    return THRESHOLDS.get(shape, POOLED)


def measured(shape: str) -> bool:
    """Whether this shape's threshold was measured or is the pooled average."""
    return shape in THRESHOLDS


def recognition_rate(shape: str, distance: float) -> float:
    """Share of people expected to name the shape, floored at chance."""
    return CHANCE + (1 - CHANCE) / (1 + math.exp(-SLOPE * (threshold(shape) - distance)))


# Bands on the measured rate rather than on raw shape distance, so the same
# words mean the same thing for a star and for a triangle.
def band(shape: str, distance: float) -> tuple[str, str]:
    """A name for how well this came out, and a sentence saying so.

    A shape nobody has rated gets hedged wording. The rate is computed from the
    pooled threshold, which is an average across a 2.7x spread, so quoting "約
    100%" for it as if raters had produced that number is the same overclaim
    this module was written to remove - just one level further back.
    """
    p = recognition_rate(shape, distance)
    if measured(shape):
        if p >= 0.90:
            return "good", f"幾乎一定認得出來（約 {p:.0%}）"
        if p >= 0.60:
            return "marginal", f"多數人認得出來（約 {p:.0%}）"
        if p >= 0.35:
            return "poor", f"大約一半的人認不出來（約 {p:.0%} 認得出）"
        return "unrecognisable", "認不出形狀了，換個城市或把距離拉長"
    # Unmeasured: same bands, but said as an estimate.
    if p >= 0.90:
        return "good", "應該認得出來（這個圖案還沒找人實測過）"
    if p >= 0.60:
        return "marginal", "大概認得出來（這個圖案還沒找人實測過）"
    if p >= 0.35:
        return "poor", "可能認不出來（這個圖案還沒找人實測過）"
    return "unrecognisable", "大概認不出形狀，換個城市或把距離拉長"
