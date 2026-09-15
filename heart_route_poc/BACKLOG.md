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
the supposed threshold, in under three seconds. So wander is a CONSTRAINT, not a term to
trade off — and POC 19 gave the reason from the other side: among fitted routes
wander and shape distance are independent (rho +0.104, p = 0.52), so optimising
one tells you nothing about the other.

Built, in `server/app.py`: fit every candidate, keep those within
WANDER_LIMIT = 0.30, pick the closest shape among them, fall back to the whole
list rather than refuse. Measured over five shapes it cuts mean wander from
0.263 to 0.240 for +0.001 of shape distance; 0.25 costs +0.013 and pushes a
shape back over 0.10.

**What is not established: that anyone can see the difference.** The raters
compared curves whose better member had wander 0, and every real route sits
between 0.19 and 0.50 — far outside the range they judged. A rater round on
real routes at different wander levels is what would settle it, and it has not
been run.

A rater asked why several shapes were "missing a corner". They were: the
deformation flattens each shape's largest outward feature, so a star loses a
point and a crescent loses a horn. Worth recording because the question is the
finding restated - a shape with a corner amputated still read as the better
one.

## 9. The coarse scan ranks nothing — POC 17, and POC 19 says why

Over thirty fitted candidates the coarse scan's rank and the final shape
distance correlate at Spearman -0.024 (p = 0.90). Stage 1 tells you which
placements are ROUTABLE, which is worth having, but among those its order is
noise — and POC 3 built the two-stage search on the premise that it ranks.

POC 19 tried to build a stage-1 score that predicts the fit and **failed at
that**, which is the useful part. Six cheap features over forty candidates: the
best correlation with final shape distance is -0.287 at p = 0.07, with a sign
that says placements further from the network fit better. There is no signal
there. Fidelity appears to be decided inside the routing, not by where the
shape is placed.

The same experiment found what stage 1 CAN see: worst gap predicts wander at
+0.355 (p = 0.025). So a cheap pre-screen for wander is possible; a cheap
pre-screen for fidelity is not.

`frac_within_s` was the feature the other findings pointed at and it turned out
constant at 1.00, because MAX_GAP_M (250 m) is already stricter than the bike
street scale (280 m). The filter was guaranteeing it all along.

Still handled by fitting six candidates instead of three, at 23 s a request.

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

## 11. DETOUR_RATIO is a best-of-thousands number (POC 23)

1.25 +-15% was calibrated on 1-3 km shapes. At 12.3 km, Taipei 101 came in
at 1.93 and a notch-free 101 at 2.18. Barriers, grid orientation and the
outline's reversals were each tested and rejected, so what is left is that a
small shape is chosen from thousands of viable placements and a large one from
27. The constant is not retuned yet, because one shape is not a calibration.

Measurement that settles it: hold the shape and its size fixed, vary the number
of viable placements the search is allowed to choose from (1, 4, 16, 64, all),
and plot achieved detour against it. If detour falls with choice, the constant
has to become a function of the size-to-network ratio, and `Plan` has to widen
its predicted range for big shapes instead of promising +-15%.

Until then the sizing model understates a large route's length by about a third,
and that is the number the product quotes to a rider.

## 5. Detour ratio as a constant — CLOSED by POC 25 and 26

Replaced by a two-term fit over sixteen measured routes:

    detour = 0.4544 + 0.0734 x width_km + 0.002079 x street_scale_m

Residual sd 0.173 against 0.339 for the constant 1.25, which had a mean error
of +0.412 — it understated, and it understated the number quoted to a rider.
At Taipei's 280 m scale the pair reproduce the Taipei-only width fit to three
decimals, which is the check that the second term describes other cities rather
than re-describing Taipei.

Sizing is now a solve, since width and detour each depend on the other.

## 12. street_scale is per place — CLOSED by POC 26

The directional street scale (median distance to the nearest street heading a
chosen way) runs 141 m in Banqiao to 223 m in Keelung and predicts what the
pipeline produces there: shape distance r = +0.74, detour r = +0.60. Cycling
only; the walking constant rests on its own nine POCs and scaling it by a ratio
measured on the bike graph would be a borrowed transfer.

## 13. Sparse cities cannot draw small shapes, and now say so

Keelung's local scale fixed its LENGTH — a 10 km request went from 15.4 km to
8.4 — but not its FIDELITY: shape distance 0.266 -> 0.18, still far above the
0.10 discrimination threshold. Its network has 4,743 nodes in a 10 km box
against Taipei's 38,615 in a 12 km one, and a heart cannot be drawn on it.

So the service reports fidelity instead of hiding it: good / marginal / poor,
on the POC 13/14 discrimination boundaries. Note those are discrimination
boundaries, NOT a measured recognisability pass mark — see #3, still open — so
the bands describe how close the route came and decline to promise anyone will
name the shape.

What is still unfixed: nothing predicts the band before the route is built. A
rider in Keelung waits a minute to be told it did not work. The coarse scan is
the natural place for that and POC 17 showed it ranks nothing (#9).

## 14. Fidelity degrades with size, unexplained

Shape distance of the kept route, heart in Taipei: 0.053 at 2.5 km wide, 0.070
at 5.0, 0.173 at 8.7, 0.127 at 12.4. The 50 km route lands at 0.109 — over the
threshold. Same cause as the detour or not, it is not measured. Rotation is
free and placement choice is ruled out (POC 24), so the candidates left are the
anchor spacing rule (WINDOW_FRACTION) and genuine network heterogeneity at
city scale.

## 3. The recognisability ceiling — MEASURED (POC 28/29), provisionally

The oldest open item. 0.10 is where a difference is SEEN; this is where the
shape stops being IDENTIFIABLE. Instrument: the route alone with no reference,
named from all five shapes at once plus "none", options reshuffled each trial,
no feedback, no score. 30 items, six per shape, 0.069–0.540. Chance 1/5.

    overall 18/30 = 60%            binomial p = 1.8e-6 against chance
    halfway point 0.220            bootstrap 95% [0.130, 0.314]
    0.00–0.10  6/7     0.10–0.16  7/9     0.16–0.22  1/2
    0.22–0.32  2/2     0.32–1.00  2/10  (= chance)

So the recognisability ceiling is roughly TWICE the discrimination threshold,
and past 0.32 there is nothing left to recognise.

Two things this changes. The service's "poor" band used to say the street
network cannot draw the shape, for anything past 0.18 — an overclaim, since the
same rater named a heart at 0.207 and a star at 0.330. There is now a fourth
band at 0.32 with wording that matches what was measured.

And the failure mode is almost entirely "cannot tell": 11 of 12 errors. Only
one was a different shape named (a triangle at 0.085, called a crescent). A
degraded route does not turn into another shape, it turns into nothing.

## 15. The threshold is not one number — it is per shape

    star5     YYYYYY   right at every level, including 0.33
    heart     YYYYnn   right to 0.21, gone by 0.33
    crescent  YYYnnn   right to 0.16, gone by 0.22
    trex      YYnnYn   erratic
    triangle  XYnnYn   erratic, and the one misnaming was at 0.085

star5 6/6 against triangle 2/6 is Fisher p = 0.061 — suggestive on one rater,
not settled. The mechanism is plausible enough to state: a five-pointed star is
unmistakable among the alternatives at any level of damage, while a triangle
with wandering edges could be several of them.

This is the same shape the project keeps finding: one constant applied where
the quantity varies (detour by size, street scale by city, and now the
recognition threshold by shape).

## 16. What more raters would buy

One rater, 30 items. The threshold interval is 0.13–0.31, wide enough that the
service's 0.18 boundary sits inside it and cannot be called wrong. Three more
raters on the same 30 items would roughly halve that interval and settle
whether the per-shape effect in #15 is real.

It also has a live dependency: the early-warning check (POC 27) is calibrated
against "unusable = 0.18 or worse", where the viable-rate signal separates with
a 30-point margin. Define unusable as 0.30 instead and the same signal stops
separating (gap −12.3%), because Taipei's 50 km heart has a 9.7% viable rate at
a distance of 0.188. Moving the boundary means recalibrating the warning.


## 3 (revised). The recognisability ceiling — MEASURED on four raters

120 judgements, 30 real routes, no reference shown, named from all five shapes
at once. Overall 70/120 = 58% against chance of 20%.

    pooled halfway point 0.201    bootstrap 95% [0.161, 0.237]
    0.00-0.10  27/28      0.10-0.16  29/36     0.16-0.22  4/8
    0.22-0.32   5/8       0.32-1.00   5/40  (= chance)

Four raters scored 60/60/57/57% — all four gave the same answer on 22 of 30
items and at least three agreed on 28 of 30, so the instrument is stable.

48 of the 50 errors were "cannot tell". Only two named a different shape. A
degraded route does not become another shape, it becomes nothing.

## 15 (revised). The threshold is per shape — SETTLED

    triangle 0.120    crescent 0.166    trex 0.169    heart 0.286    star5 0.321

One threshold for all five fits the same 120 judgements at log-likelihood
-48.1; one per shape gives -33.7. chi2(4) = 28.7, p = 9.1e-06. A factor of 2.7
between the ends.

Nothing predicts it from geometry, so a new shape must be measured. Distance to
the nearest other shape in the library: r = -0.20, Spearman p = 0.75, and the
crescent refutes it outright — the most distinctive shape in the library at
0.513 from its nearest neighbour, with nearly the lowest threshold. n_min:
r = -0.05. Unmeasured shapes get the pooled 0.201 and the service says so.

## 17. The POC 27 early warning is withdrawn

It stopped a request when fewer than half the placements fitted, calibrated
against "unusable = shape distance 0.18 or worse". POC 29 measured unusable and
it is not 0.18 and not one number. Under the measured criterion the check
blocked Taipei's 35 km and 50 km hearts — recognised by essentially everyone —
and the three genuinely unrecognisable routes do not separate from the usable
ones by viable rate at all: worst unusable 22.0%, lowest usable 9.7%, gap
-12.3%.

The underlying signal is real (log viable rate against shape distance,
r = -0.85) but it cannot carry a gate, and all three unusable cases came from
one city, so there is nothing to recalibrate on. Removed rather than retuned.

This leaves the original problem open again: a rider still waits for the fit
before learning the result is poor. What would settle it is unusable routes
from more than one city — every one in hand is Keelung.

## 18. Twelve more shapes — and the floors they carry

taiwan 2.4, leaf 5.2, house 7.9, lightning 10.4, cup 10.7, cat 12.1, fish 14.7,
music_note 14.9, plane 16.9, crown 21.0, umbrella 23.9, butterfly 26.0 km.

All twelve were fitted in Taipei (POC 30) at 1.6x their own floor and came out
between 0.050 and 0.146, so none of them is a shape that only works on paper.

Three were redrawn after being looked at rather than after being measured. The
umbrella crossed itself twice, the quaver's stem cut through its head, and the
key needed a hole - a ring is a second contour and a single closed outline
cannot carry one, so the key became a cat. The rule POC 20 found for portraits
is the same rule: if the identity is not in the silhouette it does not belong.

What is NOT known about them: their recognition thresholds. All twelve use the
pooled 0.201, which POC 29 showed is an average over a 2.7x spread, so the
service hedges the wording for them and /api/shapes reports which shapes are
measured. A pack of 30 items like POC 28's would settle six of them at a time.

## 19. n_min is a sampling floor, not a recognition floor

Taiwan comes out at n_min 8, so route_feasibility says a 2.4 km ride can draw
it. It cannot draw anything anyone would call Taiwan - the island is a smooth
blob whose sampling loss converges early, and n_min measures exactly that
convergence and nothing about whether the result is identifiable.

For the five measured shapes the gap was hidden because they happen to have
enough detail that the two floors are close. The pack makes it visible. The
honest floor for a shape is whichever is larger, and the second one is only
known after raters see it.

## 20. Description → outline: built, validated, and untested against the API

A user types 一隻兔子 and gets a shape. Claude proposes the outline;
`describe_shape.check` decides whether it is rideable, and a failure goes back
to the model with the reason rather than being repaired locally.

The checks are the record of real failures: self-intersection (three of the
twelve hand-drawn shapes crossed themselves), one contour only (a key needs its
hole; a closed curve cannot have one), and the distance floor (the veined leaf
died here — 204 km).

WHAT IS NOT TESTED: the API call. This sandbox has no Anthropic credentials, so
`/api/describe` reports `unavailable` and POC 31 exercises the loop with
hand-written proposals standing in for model output. That establishes the
checker catches the failures and the survivors draw. It establishes NOTHING
about whether the model returns good proposals or how often it needs a retry.
Both need a key.

Two of POC 31's three test cases were rebuilt after they failed to test what
they were aimed at — the "broken" boat did not actually cross (its mast was an
out-and-back, which is legal) and the over-detailed shape was rejected for
crossing rather than for cost.

## 21. The checker found three defects in shapes I had already shipped

Written to catch the model's mistakes, run first against my own: the butterfly,
leaf, music_note and umbrella each repeated their first vertex as their last
(a zero-length segment), and the quaver's flag genuinely crossed its stem — and
after that was fixed, its two flag edges crossed each other. All invisible at
render size.

Two rules in the checker itself were wrong before they were right. Counting
collinear overlap as a crossing banned the out-and-back that lets a closed
route draw any interior line at all — the leaf's midrib, every multi_contour
connector. Then `d1 != d2` treated a zero orientation as different from a
non-zero one, so a vertex lying exactly ON another segment read as a crossing:
the leaf's tip is visited by the blade, the stem and the midrib, and that
produced ten phantom crossings in a sound shape.

And `rf.n_min` is memoised on the shape NAME, so registering every candidate as
`_candidate` returned the first one's answer for all of them — a cat, Taiwan
and an aeroplane all came back n_min 36. Plausible numbers, all wrong.

## 22. The outline back end is swappable; Copilot is the default

Nothing in the description → outline loop depends on which model draws the
outline, so the model call is one function behind `BACKENDS`:

    copilot    github-copilot-sdk. Works off a GitHub account with Copilot,
               including Copilot Free. Downloads its own runtime. DEFAULT.
    anthropic  anthropic SDK, ANTHROPIC_API_KEY or an `ant auth login` profile.

Two dead ends checked rather than assumed. GitHub Models, the old free API for
exactly this, was RETIRED on 2026-07-30. And the private endpoint behind the
Copilot IDE extensions is against GitHub's terms, which license Copilot for use
in Copilot products — the SDK is the supported route and needs no scraped token.

Verified here: the SDK installs, downloads its runtime, starts, and reports
`isAuthenticated=False`. Backend selection, the unknown-backend error and the
endpoint's `unavailable` response are all exercised. The authenticated call is
NOT exercised — this sandbox has no GitHub credential — so the response
extraction (`assistant.message` → `AssistantMessageData.content`) is read off
the SDK's own generated types rather than observed on a live reply. First real
run may need that adjusted.
