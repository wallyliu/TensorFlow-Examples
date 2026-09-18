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


# ---------------------------------------------------------------------------
# What replaced the curve above, and why
#
# Everything from `CHANCE` down to `band` maps shape_distance to a recognition
# rate. POC 39 pooled every answer this project has collected - 311 judgements,
# 10 rater-sessions, 4 rounds, 62 drawings - and fitted six models of it. AIC,
# and again on the 21 drawings with at least six answers so that a per-drawing
# rate is not fitting singletons exactly:
#
#                        all 311            well-sampled 225
#     none               423.8              294.2
#     distance           414.8              281.9     <- what shipped
#     excursion          402.0              258.7
#     distance+excursion 403.9              -         (WORSE than excursion
#                                                      alone: same logL to two
#                                                      decimals, one more
#                                                      parameter. Distance adds
#                                                      NOTHING once you know
#                                                      how far the route strays)
#     drawing            305.8              190.5
#     drawing+excursion  281.3              187.9     <- best
#
# Which drawing it is beats any distance by 70 AIC. That is POC 32's
# permutation result again, arriving from a different direction: recognition is
# a property of the picture, and a curve over a distance is a worse description
# of the data than a lookup table of what people actually said.
#
# So the lookup table is what ships. `OBSERVED` is named/shown/mean excursion
# per drawing, straight out of results/poc39_recalibrate.json. Excursion stays
# as the within-shape adjustment because it earns its parameter even on top of
# the drawing (AIC 190.5 -> 187.9), at -49.7 log-odds per unit: +0.01 of
# excursion multiplies the odds of being named by 0.61.
#
# AND A SHAPE WITH NO ROW GETS NO NUMBER. The old code handed an unmeasured
# shape the pooled threshold and hedged the wording; this returns None and the
# caller says nobody has looked at it yet. An average over a set this
# heterogeneous is not a weaker estimate, it is a different shape's answer.
# ---------------------------------------------------------------------------

# name: (named, shown, the mean excursion those answers were collected at)
OBSERVED = {
    "bat": (8, 9, 0.037),
    "cat": (3, 13, 0.055),
    "christmas_tree": (11, 11, 0.046),
    "crescent": (3, 6, 0.079),
    "cup": (6, 13, 0.094),
    "e_bicycle": (0, 2, 0.148),
    "e_butterfly": (2, 2, 0.054),
    "e_cactus": (2, 2, 0.091),
    "e_crab": (2, 2, 0.054),
    "e_elephant": (0, 2, 0.043),
    "e_giraffe": (2, 2, 0.058),
    "e_maple": (2, 2, 0.032),
    "e_mushroom": (2, 2, 0.063),
    "e_penguin": (2, 2, 0.057),
    "e_turtle": (0, 2, 0.037),
    "e_whale": (0, 2, 0.037),
    "fish": (12, 13, 0.043),
    "gear": (4, 13, 0.071),
    "ghost": (6, 9, 0.082),
    "gingerbread": (0, 6, 0.082),
    "heart": (11, 11, 0.056),
    "house": (7, 13, 0.068),
    "music_note": (15, 15, 0.063),
    "plane": (15, 15, 0.049),
    "star5": (11, 11, 0.053),
    "taiwan": (5, 10, 0.092),
    "trex": (11, 11, 0.061),
    "triangle": (6, 6, 0.047),
    "witch_hat": (2, 6, 0.044),
}
EXCURSION_SLOPE = -49.7
ADJUSTMENT_CAP = 1.0   # log-odds; see `rate`
# Rounds 32 onward offered fifteen or so subjects plus "cannot tell", so a
# blind guess lands about 7% of the time. The 0.20 above is POC 29's, from a
# five-option task, and the two must not be mixed.
GUESS = 0.07


def observed(shape: str) -> tuple[int, int] | None:
    """How many people named this drawing, out of how many who saw it."""
    row = OBSERVED.get(shape)
    return (row[0], row[1]) if row else None


def wilson(named: int, shown: int, z: float = 1.96) -> tuple[float, float]:
    """The interval to quote beside a rate from fifteen answers."""
    if shown == 0:
        return (0.0, 1.0)
    p, d = named / shown, 1 + z * z / shown
    centre = (p + z * z / (2 * shown)) / d
    half = z * math.sqrt(p * (1 - p) / shown + z * z / (4 * shown * shown)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(shape: str, excursion: float | None = None) -> float | None:
    """Expected share of people who name THIS route, or None if never rated.

    The base is the observed rate with a half added to each count, so 15/15
    does not come back as certainty and 0/6 does not come back as impossible -
    neither is what fifteen or six answers support. `excursion` then moves it
    for this particular fit, from the reference the answers were collected at.
    """
    row = OBSERVED.get(shape)
    if row is None:
        return None
    named, shown, reference = row
    p = (named + 0.5) / (shown + 1.0)
    if excursion is not None:
        # Clamped, because the slope is pooled across every drawing and the
        # adjustment is an extrapolation away from where this shape's answers
        # were collected. Unclamped, a cat fitted 0.025 tighter than the ones
        # people saw comes out at 54% on the strength of 3 answers in 13 - a
        # claim nothing in the data supports. One log-odd is the most this is
        # allowed to move a measured rate.
        shift = max(-ADJUSTMENT_CAP, min(ADJUSTMENT_CAP,
                                         EXCURSION_SLOPE * (excursion - reference)))
        odds = p / (1 - p) * math.exp(shift)
        p = odds / (1 + odds)
    return max(GUESS, min(1.0, p))


def verdict(shape: str, excursion: float | None = None) -> tuple[str, str]:
    """A name for how this came out and a sentence saying so, in rater counts.

    The counts are in the sentence on purpose. "約 92%" from eleven answers and
    "約 92%" from a curve fitted to something else read identically and are not
    the same claim; "11 個人裡有 11 個認得出來" cannot be mistaken for either.
    """
    row = OBSERVED.get(shape)
    if row is None:
        return ("unrated", "還沒有人看過這個圖案，不知道認不認得出來")
    named, shown, _ = row
    p = rate(shape, excursion) or GUESS
    # Two different numbers, and they can legitimately differ - the counts are
    # this SHAPE's record, the verdict is this ROUTE. Say which is which, or
    # "大概一半的人認得出來（13 個人裡有 3 個認出來）" reads as a contradiction.
    seen = f"這個圖案給 {shown} 個人看過，{named} 個認出來"
    if p >= 0.80:
        return ("good", f"這條應該認得出來（{seen}）")
    if p >= 0.50:
        return ("marginal", f"這條大概一半的人認得出來（{seen}）")
    if p >= 0.25:
        return ("poor", f"這條多數人認不出來（{seen}）")
    return ("unrecognisable", f"這條認不出來（{seen}），換個城市或把距離拉長")


def as_good_as_rated(shape: str, excursion: float) -> bool:
    """Is this route at least as tight as the ones people were shown?

    The search used to stop early at a fixed recognition rate, which worked
    when the rate came from a curve that could reach 1.0. A measured rate
    cannot: fifteen out of fifteen answers, smoothed, is 0.97, and no shape
    with thirteen answers gets near it however well the route comes out. A
    fixed bar on that scale is not a quality test, it is a test of how many
    people have seen the shape.

    So the bar is the shape's own record instead: stop when this route strays
    no further than the average of the routes that earned the shape its rate.
    A shape nobody has rated has no record to match and never stops early,
    which is the right way round - an unknown shape is the one worth spending
    the whole search on.
    """
    row = OBSERVED.get(shape)
    return row is not None and excursion <= row[2]
