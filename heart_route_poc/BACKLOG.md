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

## 4. Feature destruction — SETTLED for the dinosaur

Three raters on an identical iso-distance ladder: the dinosaur's leg gap closed
35 / 55 / 75 / 100%, each rung matched against noise of the same shape distance.

| rung | distance | r1 | r2 | r3 |
|---|---|---|---|---|
| L1 | 0.076 | tie | tie | tie |
| L2 | 0.113 | tie | merged | merged |
| L3 | 0.146 | merged | merged | merged |
| L4 | 0.169 | merged | merged | merged |

**Eight of eight decided first-pass judgements prefer the feature-destroyed
member, p = 0.008.** With the repeats it is 14 of 14, but repeats are the same
question asked twice and are not independent, so the headline excludes them.
Self-consistency 5/6.

Equal shape distance does not mean equal damage, and the boundary is visible:
at 0.076 every rater called it a tie, from 0.113 up nobody did. Below roughly
0.08 the metric's equivalence holds; above it the metric is measuring something
people are not looking at.

Decision times say the same thing from the other side. All three took longest
on L1 — the rung they called a tie — and were fastest at the top, where the
metric insists nothing has changed relative to L1.

**The 0.060 from POC 7 does not reproduce**: filling the leg gap on the dense
template costs 0.169. POC 7 measured a 40-point fitted route, a different
operation on a different object.

**The catch trial leaks.** `scrambled` traverses the quarters out of order,
which leaves straight chords across the body, and a round-two rater asked why
some dinosaurs "suddenly have a triangle in the middle". A catch a rater can
spot by its artifact measures whether they noticed the artifact. All three
passed it, so nothing here is invalidated, but the result rests on a weaker
check than intended. `dino_wrecked` replaces it for future rounds: the same
wander as every other noise stimulus at four times L4's amplitude, so it is far
worse without being a different kind of picture.

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


## 10. The wander term measures the right thing and predicts nothing

POC 15 added `distance_v2 = shape_distance + 0.7 * wander`; POC 18 put its
predictions to two raters on three shapes it had never seen. Catches 6/6,
repeats 6/6, and the two agreed with each other on 11 of 12 trials.

**Direction: confirmed.** Seventeen of seventeen decided judgements prefer the
member with a feature destroyed over noise of the same shape distance,
p < 0.0001.

**Calibration: fails, and cannot be patched.** 7 of 24 predictions right; the
model expected 18 ties and got 2. Every "merged" answer lower-bounds the weight
and every "tie" upper-bounds it, and BOTH raters answered "merged" on crescent
L1 (needing w > 4.1) and "tie" on heart L1 (needing w < 2.6). No constant
satisfies both. The weighted-sum form is wrong, not the constant.

What the data looks like is closer to lexicographic: a crescent with a horn
sliced clean off beats one that wobbles everywhere, at a wander gap a sixth of
the supposed threshold, in under three seconds. So the next thing to try is
wander as a CONSTRAINT on the fit - reject candidates past some ratio - rather
than as a term to be traded off. Nobody has built that yet.

A rater asked why several shapes were "missing a corner". They were: the
deformation flattens each shape's largest outward feature, so a star loses a
point and a crescent loses a horn. Worth recording because the question is the
finding restated - a shape with a corner amputated still read as the better
one.

## 9. The coarse scan ranks nothing — POC 17

Over thirty fitted candidates the coarse scan's rank and the final shape
distance correlate at Spearman -0.024 (p = 0.90). The best final route sat at
coarse rank 4, 5, 2, 4 and 0 for the five shapes. Stage 1 tells you which
placements are ROUTABLE, which is worth having, but among those its order is
noise — and POC 3 built the two-stage search on the premise that it ranks.

Handled for now by fitting more of them: six instead of three, which takes the
worst of the five shapes from 0.117 to 0.097 and costs 12.6 s → 23.3 s a
request. That is a workaround, not a fix. A stage-1 score that actually
predicted the fit would buy back both the time and the quality, and nobody has
tried to build one; the obvious candidates are how much of the contour sits
within a street scale of the network rather than the mean distance to it, and
whether the placement's worst gap falls on a feature or a flat stretch.

## 8. Text does not read as text yet — and the failure is specific

Four raters' worth of reading trials, each shown a route before the word
appeared anywhere on the page:

| route | r1 | r2 | r3 |
|---|---|---|---|
| outline, nearest-point links | UT | UT | UT |
| outline, rail links | — | can't tell | **LIT** |

**Three out of three read the nearest-point outline as "UT".** That is not
noise, it is a reproducible misreading: the L and the I are being run together
into a U. It names the culprit — the link between those two letters — far more
precisely than any metric has.

The rail links produced the first correct read anyone has given this project,
after 7.5 seconds of looking. One read out of two is not a result, but it is
the first one above zero. Against that, both round-two raters answered
"neither" on both forced choices between rail and nearest-point, and the best
rating any route has received remains "not much like it".

So the rail is not established as better, and no word has been reliably read.

**Size was the remaining hope and it is gone.** POC 15 fitted LIT upright at
4.5 km and at 9.1 km, on a network widened to 14 km to hold the big one. Bigger
is not better, it is far worse: 0.094 against **0.276**, at 92 km of riding. The
picture says why — at 4.5 km the word sits inside Taipei's dense grid; at 9.1 km
it runs off the edges into the hills and the river, where there is no network to
draw with. A word is wide and short, so growing it spends everything on width
and runs out of city sideways before gaining any height.

Nothing cheap is left. Stacked lines and a taller font would attack the aspect
ratio, which is the real constraint, but both are guesses with no measurement
behind them, on a feature that has already failed a rater round. Parked.
