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
# rate. POC 39 pooled every answer this project has collected and asked, by
# five-fold cross-validation, which model predicts the NEXT answer best. Mean
# held-out log-loss per answer, 316 answers over 5 rounds and 67 drawings:
#
#     none                 0.6502
#     distance             0.6465     <- what shipped
#     excursion            0.6495
#     distance+excursion   0.6460
#     drawing              0.4850     <- best
#     drawing+excursion    0.4851
#
# NEITHER DISTANCE NOR EXCURSION IS WORTH ANYTHING. All of them sit within
# 0.005 of knowing nothing at all. Which drawing it is cuts the loss by 25%.
# POC 40 put the resolution floor - how much of a drawing lives below the scale
# a street network can hold - through the same test, and it landed EXACTLY on
# the null. See legibility.py.
# That is POC 32's permutation result arriving from another direction:
# recognition is a property of the picture, and a curve over any distance is a
# worse description of the data than a table of what people said.
#
# TWO THINGS HAD TO BE FIXED BEFORE THAT COMPARISON MEANT ANYTHING, and the
# first version of this file shipped without either:
#
#   THE POOL WAS KEYED BY NAME AND FIVE SHAPES WERE REDRAWN under theirs. The
#   gear got its centre bore between round 33 and round 37 - the rider asked
#   for it - so "gear" was two different pictures, pooled. That reported the
#   current gear as 4 named of 13 when three of three raters named it. Same for
#   the house (a door), the cup, the butterfly and the leaf. An answer now only
#   counts if the shape's minimum distance then equals its minimum now, which
#   is computed from the outline and so fingerprints the drawing.
#
#   HALF THE DRAWINGS WERE NAMED BY EVERYONE OR BY NOBODY, so a per-drawing
#   model separates the data perfectly and its coefficients run to infinity.
#   The first cut returned betas in the thousands and an excursion slope of
#   -49.7 that looked like a real effect. Under a ridge penalty the slope is
#   0.0 and the excursion term adds nothing. That number is withdrawn.
#
# So the table is all that ships. No curve, no adjustment for this particular
# route, and no number at all for a shape nobody has rated - the old code
# handed it the pooled threshold, and an average over a set this heterogeneous
# is not a weaker estimate, it is another shape's answer.
# ---------------------------------------------------------------------------

# name: (named, shown, the mean excursion those answers were collected at).
# Only the shapes the page still offers. A withdrawn subject's row is not kept
# here - `shapes.pack.WITHDRAWN_SUBJECTS` is why it went, and the answers stay
# in results/poc39_recalibrate.json, which is the record.
# The excursion is kept for `as_good_as_rated`, which is a search heuristic and
# not a claim about recognition - see there.
OBSERVED = {
    "bat": (8, 9, 0.037),
    "christmas_tree": (11, 11, 0.046),
    "crescent": (3, 6, 0.079),
    "cup": (2, 3, 0.060),
    "e_anchor": (3, 3, 0.061),
    "e_butterfly": (5, 5, 0.054),
    "e_cactus": (5, 5, 0.091),
    "e_crab": (5, 5, 0.054),
    "e_giraffe": (5, 5, 0.058),
    "e_guitar": (3, 3, 0.035),
    "e_maple": (5, 5, 0.032),
    "e_mushroom": (4, 5, 0.063),
    "e_penguin": (5, 5, 0.057),
    "e_rocket": (2, 3, 0.028),
    "e_sauropod": (2, 3, 0.028),
    "fish": (12, 13, 0.043),
    "gear": (3, 3, 0.076),
    "ghost": (6, 9, 0.082),
    "heart": (14, 14, 0.051),
    "house": (3, 3, 0.055),
    "music_note": (15, 15, 0.063),
    "plane": (15, 15, 0.049),
    "star5": (14, 14, 0.050),
    "taiwan": (5, 10, 0.092),
    "trex": (14, 14, 0.062),
    "triangle": (6, 6, 0.047),
}
# Rounds 32 onward offered fifteen or so subjects plus "cannot tell", so a
# blind guess lands about 7% of the time. The 0.20 above is POC 29's, from a
# five-option task, and the two must not be mixed.
GUESS = 0.07


def observed(shape: str) -> tuple[int, int] | None:
    """How many people named this drawing, out of how many who saw it."""
    row = OBSERVED.get(shape)
    return (row[0], row[1]) if row else None


def wilson(named: int, shown: int, z: float = 1.96) -> tuple[float, float]:
    """The interval to quote beside a rate from a handful of answers."""
    if shown == 0:
        return (0.0, 1.0)
    p, d = named / shown, 1 + z * z / shown
    centre = (p + z * z / (2 * shown)) / d
    half = z * math.sqrt(p * (1 - p) / shown + z * z / (4 * shown * shown)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(shape: str) -> float | None:
    """Expected share of people who name this shape, or None if never rated.

    Half is added to each count, so 15/15 does not come back as certainty and
    0/6 does not come back as impossibility - neither is what fifteen or six
    answers support. Nothing about the particular route enters: POC 39 found
    every route-level measure worth less than 0.005 of log-loss against knowing
    nothing, so a per-route adjustment would be decoration.
    """
    row = OBSERVED.get(shape)
    if row is None:
        return None
    named, shown, _ = row
    return max(GUESS, (named + 0.5) / (shown + 1.0))


def verdict(shape: str) -> tuple[str, str]:
    """A name for how well this shape reads, and a sentence saying so.

    The counts are in the sentence on purpose. 「約 92%」 from eleven answers
    and 「約 92%」 from a curve fitted to something else read identically and
    are not the same claim; 「11 個人裡有 11 個認得出來」 cannot be mistaken
    for either.
    """
    row = OBSERVED.get(shape)
    if row is None:
        return ("unrated", "還沒有人看過這個圖案，不知道認不認得出來")
    named, shown, _ = row
    p = rate(shape) or GUESS
    seen = f"這個圖案給 {shown} 個人看過，{named} 個認出來"
    if p >= 0.80:
        return ("good", f"多數人認得出來（{seen}）")
    if p >= 0.50:
        return ("marginal", f"大概一半的人認得出來（{seen}）")
    if p >= 0.25:
        return ("poor", f"多數人認不出來（{seen}）")
    return ("unrecognisable", f"幾乎沒有人認得出來（{seen}）")


def as_good_as_rated(shape: str, excursion: float) -> bool:
    """Is this route at least as tight as the ones people were shown?

    A SEARCH HEURISTIC, NOT A RECOGNITION CLAIM. POC 39 found excursion no
    better than knowing nothing at predicting whether a person names a route,
    so this does not say the route will read - it says the search has found
    something no worse than what was put in front of raters, and can stop.
    That is all a stopping rule needs to do, and it took a 25 km gear from 20
    seconds to 6.

    It replaced a fixed recognition rate of 0.97, which a measured rate cannot
    reach: fifteen out of fifteen answers, smoothed, is 0.97, and no shape with
    thirteen answers gets near it however well the route comes out. That bar
    was testing how many people had seen the shape, not the route.

    A shape nobody has rated has no record to match and never stops early,
    which is the right way round - an unknown shape is the one worth spending
    the whole search on.
    """
    row = OBSERVED.get(shape)
    return row is not None and excursion <= row[2]
