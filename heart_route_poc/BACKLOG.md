# Backlog — deferred, with the reason

Things measured or reasoned about but not built. Kept here so they are decisions
rather than omissions.

## 1. Multi-contour shapes — SOLVED, see `multi_contour.py`

**What it was.** Every stage of the pipeline takes ONE closed curve:
`shape_library`, `place_shape`, the Viterbi matcher, `shape_distance`. A shape
with a hole or a separate part could not be expressed. POC 8 measured Chrome's
dinosaur eye at 13×12 px — 6.4% of the shape's width, or 128 m at a 2 km target,
comfortably above the ~50 m this street network resolves. It was not too small to
draw; it was structurally unrepresentable. The same limit blocked text-to-shape:
LOVE is 5 closed contours, TAIPEI is 8, and `A B D O P Q R` all have counters.

**The fix, and whose it was.** The user's, not the metric's: link the contours
with the shortest connectors and ride each connector out and back. The result is
one closed curve, and nothing downstream needs to change — not the metric, not
the search, not the fit. The product question this item said had to be answered
first ("two walks? a marked gap? a connecting leg?") turned out to have a fourth
answer that made it moot.

**What it cost, measured** (`poc11_onestroke.py`): the connectors add 5.6% of
perimeter for LIT, 6.1% for LOVE, 10.0% for TAIPEI, and are hairlines on the map.

**What it did not fix.** Distance. Merging is cheap; words are not. n_min tracks
features, not contours: LIT 84, LOVE 160, TAIPEI 240, which at the bike street
scale is 30 / 56 / 85 km and needs the word drawn 4.5 / 7.7 / 10.7 km wide. A
word is wide and short, so its strokes end up closer together than the street
scale can resolve. **The blocker moved from topology to distance** — which is
item 6 below, and a different kind of problem.

## 2. Are these routes actually walkable? — the untested risk

**What.** Nobody has verified a single generated route against reality, or even
against street-level imagery.

**Why it matters.** osmnx's `walk` filter admits footways, steps, corridors and
service alleys. POC 1's own diagnostics found a snapped node whose edges were
`['steps', 'footway', 'corridor']`. A route may pass through a building's
interior passage, an underpass locked at night, or a construction site. Every
metric in this project measures shape fidelity; none measures whether a person
can complete the walk.

**Cheapest first step** (no fieldwork): tabulate the `highway` tags along a
generated route and report what fraction sits on steps, corridors, service ways
and paths tagged `access=customers` or similar. That alone would size the
problem.

## 3. The recognisability ceiling — still unmeasured

POC 6's v2 threshold task anchored every pair to the clean route, which
guaranteed one good member and so recorded zero "neither looks like it" answers.
Measuring where a shape stops reading as itself at all needs **unanchored pairs
AND the four-option response together** — the two fixes have never been in the
same instrument.

## 4. A rater round on feature destruction — run once, needs more raters

POC 13 put it to a fresh rater as an iso-distance ladder: the dinosaur's leg gap
closed 35 / 55 / 75 / 100%, each rung matched against noise of identical shape
distance. The rater called the two bottom rungs a tie and preferred the
feature-destroyed member at both top rungs, including on both repeat trials —
4 of 4 decided judgements in the same direction, sign test p = 0.125. The catch
trial passed.

Direction as predicted, significance not reached. One rater, four decided
judgements; p = 0.125 is the *floor* for 4/4, so no single rater could have
settled this however lopsided their answers. Needs three or four more raters on
the same ladder, which is built and takes five minutes.

Two things the round did settle. The "neither" option is reachable — it was used
on an unanchored text pair, which closes the instrument half of item 3. And the
0.060 figure quoted here from POC 7 does not reproduce: filling the leg gap on
the dense template costs 0.169, not 0.060. POC 7 measured it on a 40-point
fitted route, which is a different operation on a different object, and the two
numbers were never comparable.

## 5. Detour ratio as a constant

`route_feasibility` assumes ~1.30. Stable across five shapes at 2 km, and
validated in POC 9 across sizes — but it is an empirical constant from one city,
and a different street grid would move it.
## 6. Words are too long to ride — the new text blocker

Following from item 1. Four directions; one is now tested and dead.

**Tested, and it does not help: a single-stroke font.** POC 12 built one (26
glyphs, `stroke_font.py`) on the reasonable guess that one line down the middle
of each letter would be cheaper than tracing both edges. It is not. A line with
no thickness has to be ridden out and back, so it costs 2× its length — which is
roughly what an outline's perimeter already is. Measured at equal width the two
styles are within 7% (LIT 0.93, LOVE 1.05, TAIPEI 0.96). Worse, n_min rises
27–43%, because with everything a thin line the connectors from item 1 become
indistinguishable from letter strokes: in LIT the link between the I's top bar
and the T's top bar is collinear with both and fuses the letters. Shipped as a
user-selectable style regardless — wanting it is legitimate — but it is not a
route to shorter rides.

**Untested:** short words only (a feasibility gate that rejects TAIPEI before
drawing it, which `route_feasibility` can already do); a taller font or stacked
lines, to spend width on height instead of length; or accepting a multi-day /
multi-segment route, which is a product decision, not an algorithmic one.


## 7. The metric is wrong for text — rotation must be a constraint

POC 12 fitted "LIT" to the bike network with rotation free, as every POC since 6
has done. The search returned tilted placements and `shape_distance` scored them
well — outline 0.066, stroke 0.124 — and neither reads as a word. Forced
upright, the routes read as letters and the metric scored them *worse*, 0.114
and 0.164. For text the metric is not merely blind to orientation, it prefers
the unreadable fit.

Rotation invariance was not a mistake when it was adopted: POC 5's rater called
tilted and upright hearts equally heart-like, and POC 6 built the search on
that. It is simply not a property of every shape. The shape has to carry its own
orientation constraint — free for a heart, fixed for a word, probably a narrow
band for a dinosaur — and the metric needs an orientation term for the shapes
that have one. Neither exists yet.

Until then `poc12_word_routes.py` pins `ROTATIONS_DEG = (0.0,)` by hand.


## 8. Text does not read as text yet — orientation is not the reason

POC 12 predicted the metric was inverted for text and POC 13 tested it. The
result is worse than inverted and simpler: the rater could not read any of the
four LIT routes. Shown the upright outline route before the word appeared
anywhere on the page, they answered "UT" after 8.9 seconds; shown the upright
single-stroke route, "can't tell". Told afterwards that the word was LIT, the
best rating any of the four received was "not much like it", and one pair drew
"neither".

The orientation claim itself did not replicate cleanly: the rater rated the
upright outline above the tilted one, then picked the tilted one in a forced
choice between the same two images. One rater contradicting themselves on two
trials settles nothing either way.

So the open question is no longer which orientation reads better. It is whether
a word at this size, on this street network, can read as a word at all — and
the first evidence says no. Worth knowing before any more work goes into
stacked lines, taller fonts, or an orientation term in the metric.