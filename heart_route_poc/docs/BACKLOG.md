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

## 23. The shape metric is blind to the features that carry identity

`shape_distance` is an RMS over the whole contour, so it is dominated by the
gross outline. Ears, teeth and tails are a small fraction of arc length, and
losing them costs almost nothing. Measured by low-passing each outline to k
Fourier harmonics and scoring the result against itself:

| shape    | k=3 (a smooth blob) | k=8 | k=20 |
|----------|--------------------:|----:|-----:|
| gear     | 0.125 | 0.125 | 0.026 |
| cat      | 0.248 | 0.073 | 0.024 |
| triangle | 0.073 | 0.021 | 0.008 |

A gear with **no teeth at all** — an ellipse — scores 0.125, which the
recognition curve reports as 98.5% recognisable. The real 30 km gear came out
at 0.101 with sixteen teeth missing and was reported "應該認得出來".

Two consequences. The thresholds in `recognition.py` were measured on five
shapes whose identity IS their gross outline (triangle, heart, star, crescent,
T-rex), so applying the pooled 0.201 to a detailed shape uses the wrong ruler.
And `n_min` is computed from the same blind metric, so `min_km` permits sizes
at which the features are physically smaller than a city block.

Proposed fix, not yet built: a second distance computed on the HIGH-FREQUENCY
residual of the contour, reported alongside the first, so that losing the teeth
is expensive. Measure before wiring it into the search.

## 24. Seven of fourteen shapes were wrong, and the validator passed all of them

`describe.check()` validates a polygon: no self-crossings, sane aspect ratio, a
floor somebody will ride. It has no opinion on whether the drawing looks like
its name, and there is no mechanical test that does. Every shape in the pack
passed it; the first person to look at them rejected half.

Nothing was geometrically wrong. Each failure was a CONVENTION failure — the
outline did not match the picture a reader would draw:

| shape | read as | what was actually missing |
|---|---|---|
| cat | Pikachu | a neck notch and a muzzle |
| crown | mountain range | vertical sides, a band, balls on the points |
| gear | the sun | flat tooth tops and flat valleys, half as many teeth |
| fish | a leaf with a thorn | a caudal fin at a fish's proportion |
| butterfly | — | the local convention; the first two redraws read as a bat and a heart |
| rabbit | nothing | face-on symmetry instead of a profile |
| house | generic | eaves, a chimney, a door |

And the convention is local: a butterfly was rejected as 跟台灣的習慣畫法差很多.

Redrawing for legibility also made every one of them cheaper to ride, because
the features that do not read are exactly the ones that cost distance:

| shape | floor before | after |
|---|---:|---:|
| gear | 22.0 km | 10.5 km |
| butterfly | 26.0 km | 21.3 km |
| crown | 21.1 km | 14.7 km |
| fish | 14.7 km | 11.0 km |
| rabbit | 9.0 km | 8.9 km |

Still open: the twelve pack shapes have no measured recognition threshold, and
nobody has yet seen any of them WITHOUT its label. That test is the only thing
that would have caught the cat.

## 25. "No feature smaller than 10% of the width" — proposed, measured, refused

The rule looked obvious and it is wrong. Measured as the smallest distance
between two boundary points far apart along the boundary, over the shape's
width, the five shapes raters actually identify score 0.098 (heart), 0.095
(star), 0.053 (crescent), 0.074 (T-rex), 0.057 (Taiwan) — a 10% gate throws out
all of them. The measure conflates a sharp CORNER, which draws perfectly well,
with a thin sliver, which does not.

`metrics.thinness` is the version that survives: minimum chord over arc between
the same pairs. A corner of interior angle t scores sin(t/2) however sharp it
is; a sliver scores its own width over its own length. On that scale the
identified shapes bottom out at 0.130 and the features that have actually
vanished (butterfly antennae 0.041, lightning 0.031, leaf midrib 0.001) sit far
below.

It is still NOT a gate, and `check()` reports it as a note rather than a
problem: a cat at 0.070 drew its tail correctly at 30 km and lost it at 50 km,
so what a low score buys is a longer ride, not a refusal — and how much longer
is unmeasured. An uncalibrated signal that rejects work is worse than none.

## 26. A tail cannot be drawn, and a cat is its head

Four cats were drawn before one survived, and the sequence is the argument:

1. tall pointed ears, round body, no neck — read as Pikachu by everyone.
2. a sitting profile with a neck notch, a muzzle and a curled tail — correct
   in every part, and still "超級不像". A cat seen side on is a shape any
   four-legged animal makes.
3. the head alone, at cartoon proportion — the best-behaved shape in the pack.
4. that head on a small body with a thick tail — shipped as `cat`, because a
   person looking at it said it was cute, which is the only evidence that
   counts here.

Budget is the lesson. Half the contour of a sitting cat goes on a body, a
foreleg and a haunch that carry no identity, and a cat's identity is two
triangles on a head. Spending the points on the head instead:

| | floor | n_min | thinness | best fit in Taipei |
|---|---:|---:|---:|---|
| sitting profile | 12.2 km | 36 | 0.070 | 0.056 @ 28.5 km |
| `cat` (head + body + tail) | 10.6 km | 32 | 0.066 | — |
| `cat_head` | **7.8 km** | 24 | **0.390** | **0.036 @ 24.4 km** |

0.036 is the closest fit this project has produced for any shape, and at 10 km
`cat_head` still comes out at 0.117 with both ears.

THE TAIL IS NOT SOLVED. A tail is a stroke; a closed outline can only draw a
stroke as a long thin loop, which is either too thin for the streets to render
or thick enough to read as a leg. Three attempts all produced a hook hanging
off the side. The shipped one is the thickest at 14% of the width and scores
0.066 on `metrics.thinness`, below the warning line. Same wall as the butterfly
antennae, the leaf midrib and the umbrella rim — four shapes, one cause.

A FACE IS POSSIBLE AND NOT WORTH IT. `multi_contour` carries eyes and a nose
into the single closed curve and they do render — measured at 40 km, fit 0.067.
But n_min goes 24 → 92 and the floor 7.8 km → 34.3 km, and the connectors the
merge needs cross the cheek as visible lines. Four times the ride for a face
with a scar through it. Dropped.

`cat` and `cat_head` both ship. Which is actually more recognisable is a
question for raters, not for whoever drew them, and both go into the blind test.

## 27. Recognition is a property of the DRAWING, not of the shape distance

Two raters, 30 items each, 15 shapes. They agree on 25 of 30 items (kappa
0.67), so the splits below are about the shapes rather than about the people.

Per-shape accuracy does not look like the same answers dealt out at random:
variance 0.177, permutation p < 0.0001 over 20,000 shuffles. It is close to
trimodal.

| | shapes |
|---|---|
| 4/4 correct | butterfly, cup, fish, music_note, plane |
| 0/4 correct | cat_head, crown, lightning, rabbit, umbrella |
| mixed | leaf 0.50, taiwan 0.50, cat 0.25, gear 0.25, house 0.25 |

Accuracy against shape distance, over the same answers: 50% below 0.07, 50% to
0.10, 50% to 0.14, 36% to 0.20, 33% above. Flat where the per-shape split is
sharp.

THIS BREAKS recognition.py's model. It gives every shape a logistic curve over
shape distance with a per-shape threshold, and fits the five original shapes
well - POC 29 measured 96% below 0.10 falling to 12% above 0.32. For the pack
the curve is the wrong object: five of these shapes are never recognised at
any distance the router can reach, and five always are. A threshold describes
a shape whose identity IS its gross outline. For the rest the question is
binary and settled before any route is fitted.

Do not repair the curve by fitting per-shape thresholds to four answers each.
What the service should say is which of the three groups a shape is in, and it
should say "unmeasured" until raters have seen it.

AND THE SAME DISTANCE MEANS DIFFERENT THINGS. Below 0.10 - the closest this
project fits - the original five scored 27/28 and this pack 16/32 (Fisher
p = 0.00005, odds ratio 27). This is BACKLOG 23 appearing in human data: 0.07
on a triangle is a triangle anybody names, 0.07 on an umbrella is nothing.
Confounded, though: POC 29 offered five options against this task's sixteen,
and the raters differ. Anchor items - the original five inside THIS task, same
options, same raters - would settle it, and are the next thing to build.

THE REDRAWS DID NOT ALL WORK, and the record is mixed in both directions:

  redrawn, now recognised     butterfly, fish
  redrawn, still not          crown, rabbit, cat_head
  redrawn, mixed              cat, house, gear
  never redrawn, recognised   cup, music_note, plane
  never redrawn, not          lightning, umbrella

Four of the five failures had been redrawn and approved by eye in the round
before this one. That is the whole argument for the task: knowing the answer
and then looking is a different act from looking.

31 of the 33 errors were "cannot tell". Routes do not become the wrong thing;
they become nothing. Same as POC 29's 48 of 50.

## 28. Choose subjects by the diagnostic feature, and retire the five that failed

POC 32's split is the rule for picking what to draw next. The five shapes
named every time each carry one part nothing else has — a handle, a forked
tail, a cruciform, a flag, four lobes. The five never named are assembled
entirely from generic parts:

| retired | what it actually is |
|---|---|
| crown | a zigzag on a trapezoid, which is a mountain range |
| lightning | a zigzag, which is an arrow |
| umbrella | a dome on a stick, which is a mushroom, or a tree |
| rabbit | a blob with ears, which is any animal |
| cat_head | a blob with ears — its one misidentification was as `cat` |

So being distinctive OVERALL is not enough, and neither is being drawn
correctly: the reader needs one place to put their finger. All five are out of
`PACK` and kept in `RETIRED`, because what each one lacked is a finding and a
redraw that gives it a diagnostic feature can put it back.

Six seasonal shapes chosen by that rule, all fitted in Taipei:

| shape | floor | thinness | fit |
|---|---:|---:|---|
| gingerbread | 9.1 km | 0.223 | 0.055 @ 20.3 km |
| witch_hat | 7.9 km | 0.250 | 0.083 @ 14.9 km |
| snowman | 10.3 km | 0.137 | 0.107 @ 20.3 km |
| ghost | 13.8 km | 0.354 | 0.109 @ 19.8 km |
| christmas_tree | 15.2 km | 0.207 | 0.085 @ 22.6 km |
| bat | 19.9 km | 0.100 | 0.118 @ 25.5 km |

The gingerbread man replaces the rabbit and is the argument for the rule: a
symmetric body with four stubby limbs stuck straight out has no neighbours,
where a blob with ears has every animal. It is also the cheapest recognisable
figure here, 9.1 km against the rabbit's 8.8 for a shape that was never named.

Two drawings failed on the way and both failed the same way. A Santa hat, at
three drafts, and a witch hat drawn leaning, both read as a BOOT: a tilted cone
rising from a horizontal base is a boot's profile. Upright and symmetric the
witch hat is a hat again; the Santa hat was abandoned.

Christmas tree: the tiers alone are a mountain range, which is exactly how the
crown failed. The trunk is the part a mountain has not got.

NONE OF THE SIX IS MEASURED. They were chosen by a rule derived from two
raters and drawn by the same person whose eye has now been wrong four times in
a row. They go into the next blind round, with anchor items, before any of
this is believed.

### 28a. What the second look changed

The six were shown to the same person who had just judged the last round, and
four came back with a specific complaint each. All four were right and all four
cost distance to fix, which is the trade this project keeps making:

| shape | complaint | fix | floor |
|---|---|---|---:|
| snowman | too thin | a third wider; aspect 1.93 to 1.42 | 10.3 -> 18.2 km |
| christmas_tree | clear, but not CHRISTMAS | a five-pointed star on top | 15.2 -> 18.3 km |
| witch_hat | the brim is too thin | brim 0.20 to 0.28 of the height | 7.9 -> 5.0 km |
| ghost | cannot tell, probably no eyes | two eyes via multi_contour | 13.8 -> 27.6 km |

The star had to be COARSE. A finely drawn one took the tree to 38.6 km by
itself; five big points at a fifth of the tree's width cost 3 km.

The ghost is the exception to POC 20's rule that identity must be in the
silhouette. A dome with a wavy hem is a blob - scoring 0.354 on thinness, the
cleanest outline in the pack, and still unreadable. It is the one subject here
worth paying an interior for, and it costs double. The connectors are cheaper
to look at than the cat's were, because they run horizontally into the eyes
from the stub arms rather than diagonally across a face.

Re-fitted in Taipei: snowman 0.073 @ 24.2 km, christmas_tree 0.111 @ 23.3,
ghost 0.093 @ 31.9, witch_hat 0.083 @ 10.4. The gingerbread man and the bat
were accepted unchanged.

## 29. The anchors hold: within one task the pack loses to the original five

POC 32's comparison across two tasks was confounded twice - five options
against sixteen, and different people. POC 33 puts the original five INSIDE the
same task, 21 shapes, 42 items, one option list. First rater:

| | named | below d=0.10 |
|---|---|---|
| the original five (anchors) | 9/10 = 90% | **5/5** |
| this pack | 11/32 = 34% | 8/17 |

Fisher p = 0.054 on one rater, odds ratio infinite because the anchors did not
miss a single close fit. The option count rose from 16 to 21, which makes
everything harder - and the anchors still scored 90%, which is what an anchor
is for. The effect POC 32 measured survives losing both confounds.

So BACKLOG 23 is confirmed in human data as far as one rater can confirm
anything: 0.07 on a triangle is a triangle anybody names; 0.07 on a cup, a
snowman or a gingerbread man is nothing. shape_distance is not a recognition
scale for shapes whose identity is not their gross outline.

The new scalloped Christmas tree was named at both 0.081 and 0.164 - the only
seasonal shape this rater got - which is some evidence the star did its job.
The other five seasonal shapes went 0/2 each, as did cup, which had been 4/4 in
POC 32 on the same pictures. One rater at two items per shape cannot separate
that from noise; the anchor comparison is within-subject and does not depend on
it.

## 30. The gear needs a hole, and that is two exceptions to POC 20 now

Across POC 32 and 33 the toothed ring was named 1 time out of 6, and the
complaint both times was the same: a gear has a hole. `multi_contour` puts one
in - the route rides a spoke to the bore, round it, and back out - at a cost of
10.5 km to 22.4. A 0.20 bore reads better and costs 29.1; 0.16 is the cheapest
that is unmistakably a gear.

Second shape to need an interior after the ghost, and for the same reason. POC
20's rule is that identity lives in the silhouette, and it holds for most
things; the exceptions are shapes whose silhouette is a blob that something
INSIDE distinguishes - a ring of teeth, a dome with a wavy hem. Both cost
roughly double the ride, and both are worth it, because the alternative is a
20 km route that nobody can name.

## 31. A single spur is worth more than the whole shape distance

A rater looked at a route that is a perfect Taiwan except for one straight bar
shot across the bottom right, and answered "cannot tell", naming the bar. Three
of the six Taiwan routes in POC 33 carry one. They come out of the map
matching: two consecutive contour points land either side of something the
street network cannot cross, the shortest path between them runs a long way
round, and the route draws a spike into the interior.

Nothing in the pipeline sees it. `shape_distance` compares resampled positions,
so a spike moves a handful of points and costs almost nothing. `wander` is a
ratio over the whole route, and a 1 km spur on a 25 km ride is 4% against a
limit of 30%. Both are averages. A spur is a maximum.

`metrics.excursion` is the maximum instead - the farthest any route point
strays from the template, over the shape's width. Against the POC 33 answers,
84 of them over 42 routes from two raters:

| | correct | wrong | Mann-Whitney |
|---|---:|---:|---|
| max excursion | 0.048 | 0.062 | **p = 0.013** |
| shape distance | 0.081 | 0.112 | p = 0.142 |

The measure the entire search optimises does not separate the routes people can
name from the ones they cannot. This one does.

NOT YET A GATE. Within a fixed distance band the direction holds and the
significance does not (p = 0.085 below 0.10, p = 0.098 above), and the two
correlate at Spearman 0.77 - so this is not yet evidence that excursion adds
anything beyond distance. Reported, like `thinness`, and the reason to collect
more answers. The version of this that ships is a constraint in `search`, the
way `WANDER_LIMIT` is, and it should not ship on n = 84.

## 32. What the second rater's five complaints were actually asking for

Three of the five asked for the same thing: an interior line.

| complaint | what it means | floor |
|---|---|---|
| butterfly needs "a line top to bottom" | the abdomen | 21.3 -> 34.3 km |
| the house door needs "a line under it" | a door is a rectangle on the floor, not a hole in the wall | 14.0 -> 22.0 km |
| the leaf needs more veins | venation | refused, see below |
| the cup's handle is too thin | 6% of the width | 10.7 -> 12.3 km |
| Taiwan has "an extra bar at the bottom right" | a routing spur, not the shape | BACKLOG 31 |

The butterfly's spine is the most expensive single line in the pack, because a
zero-width feature is the finest feature there is and n_min tracks fineness
rather than quantity. The same arithmetic is why the leaf's veins are refused:
one pair costs 61 km, two cost 90, and a serrated margin tried in their place
costs 58. What the leaf needed was not veins but ASYMMETRY - it was called
lips, and lips are symmetric both ways while a leaf is symmetric only about its
midrib. Redrawn ovate, wide at the stem and tapering to the tip, it goes from
20.5 km to 9.1: more leaf-like and less than half the ride, the only change in
this round that was not a trade.

## 33. Weighting the matcher per contour point: feasible, and the weights compute

Proposed: make some contour points matter more, so the route MUST hit them and
can relax elsewhere. The plumbing is one line - `viterbi_closed_loop` already
multiplies every emission by a single global `snap_weight`, so a per-point
weight is that constant becoming an array. The open question was the numbers.

POC 34 computes them by flattening one region of the outline at a time,
replacing it with the straight chord across it, and measuring what that costs.
Two candidates:

  SELF            how much shape_distance to the shape's own template rises.
                  Close to curvature - and curvature is not identity. The crown
                  is all corners and raters named it 0/4.
  DISCRIMINATIVE  how much closer the flattened shape moves to its nearest
                  OTHER shape in the library. This asks what stops it being
                  something else, which is exactly the rule POC 32 produced.

The discriminative map finds the right parts: the cup's handle root, the
plane's wingtips, the gear's CENTRE HOLE - the thing a rater said was missing
before it had one - and the crown's deep valleys rather than the flat base it
shares with every trapezoid.

Two ways to spend it, and the second is cheaper:

  1. per-point `snap_weight` in the Viterbi pass. One line, and it changes
     nothing else.
  2. non-uniform RESAMPLING - put more of the same `points` budget on the
     high-saliency arcs and fewer on the straight runs. No change to the
     matcher at all, and it should relieve n_min too, since n_min is set by the
     finest feature and this is a way of spending samples where fineness lives.

THE BLOCKER IS EVALUATION, NOT IMPLEMENTATION. Weighting the matcher makes the
route hug the parts that carry identity at the cost of the parts that do not,
so the route will score WORSE on unweighted `shape_distance` while looking
better. There is no way to validate it against the metric - and BACKLOG 29 has
already established the metric is the wrong ruler for these shapes, 90% against
41% at equal distance. So this ships only behind a rater round: same shapes,
weighted against unweighted, blind.

## 34. Excursion becomes a constraint; it is the first one fitted to people

Three raters, 126 answers. At n = 84 the excursion signal was a lead; at 126 it
is decisive, and the reason is that it separates WITHIN a fixed shape-distance
band, which is what "carries information the metric does not" means:

| | correct | wrong | |
|---|---:|---:|---|
| excursion, all | 0.050 | 0.080 | p < 0.0001 |
| excursion, d < 0.10 | 0.043 | 0.060 | p = 0.0009 (n=66) |
| excursion, d >= 0.10 | 0.071 | 0.103 | p = 0.0001 (n=60) |
| shape distance, all | 0.081 | 0.118 | p = 0.087 |

Naming rate by excursion band: 67% below 0.040, 74% to 0.055, 67% to 0.070,
52% to 0.090, and **21% above**. The cliff is at 0.09.

`EXCURSION_LIMIT = 0.08` keeps 71% of fitted placements, which were named 67%
of the time against 25% for the ones it drops, and with six candidates a
request nearly always has one under it. Applied lexicographically like
WANDER_LIMIT, falling back rather than refusing.

This is the first constraint in the project fitted to what people RECOGNISE
rather than to what the metric scores, and it had to be: shape distance alone
does not separate named from unnamed in this data at all.

ONE BUG, CAUGHT IN VERIFICATION. Wander is a length ratio, so the call that
builds its template has always passed rotation 0, and the first version of the
excursion call copied that. Excursion is a nearest-point distance and
orientation is most of it: a correctly fitted Taiwan scored 0.253 against an
upright template, which is the rotation and not a spur. It now gets the
template the matcher actually aimed at, and the same route scores 0.035.

## 35. Three shapes are unnamed after every fix, and one of them was my prediction

After three raters, 0/6 with no fix pending: cat, gingerbread, snowman. (cup,
gear and leaf were also 0/6, but their stimuli used versions since redrawn on
the raters' own feedback, so they are untested rather than refuted.)

The gingerbread man is the uncomfortable one. It was the worked example for the
rule POC 32 produced - a symmetric body with four stubby limbs stuck straight
out has no neighbours - it was the cheapest recognisable figure in the pack at
9.1 km, and it scored 0/6. The rule that predicted it is the same rule that
correctly retired the crown and the rabbit, so it is not worthless, but it is
clearly not sufficient, and it was mine rather than the raters'.

What the three have in common is worth testing rather than asserting: all three
are figures whose parts are individually generic (a head, a body, limbs, balls)
and whose arrangement is supposed to carry the identity. The shapes that pass -
plane, music note, Christmas tree, bat, fish - each have one part that is
strange on its own.

## 36. The veins are refused again, on better numbers, and answered a different way

Two raters have now asked the leaf for veins - "a few horizontal lines, not
just the one". The old refusal was measured on the LENS-shaped leaf, and that
leaf has since been replaced by an ovate one at less than half the price, so
the question was worth re-asking on the cheaper base. Re-measured:

| | floor |
|---|---:|
| midrib only | 9.1 km |
| 1 pair | 43.5 km |
| 2 pairs | 115.3 km |
| 3 pairs | 166.6 km |

So the answer is the same and the reason is sharper: n_min tracks the finest
feature, a vein is a zero-width stroke, and each one you add is SHORTER than
the last, so "several" costs 115 km and up. One pair at 43.5 km is the most
this approach can give and it is a long day for two lines.

`maple` answers the same request differently. Its lobes are OUTLINE features,
costing what a notch costs rather than what a stroke costs: 13.8 km, and
`metrics.thinness` 0.257 against the veined leaf's effectively zero. It is also
the leaf most people draw.

Both ship. `leaf` stays at 9.1 km as the cheap one, `maple` is the one that
should read without help, and the raters decide - the same way `cat` and
`cat_head` were handled. One risk named in advance: five points around a centre
is also a star, and `star5` is in the library; the stem and the notched margin
are what separate them.

## 37. Pick animals with one strange part

POC 33's split, three raters, six answers per shape:

    named 6/6   plane, music note, Christmas tree   (+ every anchor)
    named 5/6   bat, fish
    named 0/6   cat, gingerbread man, snowman

The pattern is not distinctiveness overall. Each shape that passes carries one
part that is strange ON ITS OWN - a cruciform, a flag, a star on a trunk, a
scalloped wing, a forked tail. Each shape that fails is a FIGURE built from
parts that are individually generic - a head, a body, limbs, balls - where the
identity is meant to live in the arrangement. Arrangement does not survive
being drawn in streets.

So the next animals are chosen by which strange part they own, and by whether
that part is THICK, since a thin one cannot be drawn at all (BACKLOG 26):

| shape | the strange part | floor | thinness |
|---|---|---:|---:|
| crab | two raised claws | 10.7 km | 0.107 |
| elephant | a trunk, and an ear | 13.5 km | 0.138 |
| giraffe | a neck four times the head | 13.6 km | 0.125 |

All three are cheaper than the gingerbread man's 9.1 km was worth, and all
three are untested - they go into the next blind round with `maple` and with
the redrawn cup, gear and leaf.

The giraffe's legs are deliberately short and thick. A giraffe's real
proportions put four sticks under it, and thin is what the streets refuse; the
neck is what carries the name, so the neck gets the width.

The elephant's trunk crossed its own chest on the first draft. A hanging
appendage is traced down one side and back up the other, and the two edges must
not swap sides on the way - the same mistake the cat's tail made three times.

## 38. Stop drawing; trace the emoji. And stop treating a low floor as a win

Seventeen hand-drawn shapes were rejected on sight against five that passed.
BACKLOG 24's rule is right - draw the picture people would draw - but the hand
doing the drawing was mine. The emoji is that picture, agreed by committee and
already installed on this machine.

Noto Color Emoji is a bitmap font with no outlines to read, so the silhouette
is traced out of the rendered glyph: alpha threshold, fill holes, largest
component, Moore-neighbour boundary follow, Douglas-Peucker.

SIMPLIFY TO A TOLERANCE, NOT A VERTEX COUNT. A fixed budget spends the same 44
points on a mushroom and a crab. A tolerance - stay within this fraction of the
width - lets the count follow the subject: at 1%, 28 points for a mushroom and
97 for a crab.

AND FINER IS USUALLY CHEAPER, which is the wrong way round from the intuition
this project has been running on:

| | 3% tol | 0.7% tol |
|---|---|---|
| elephant | 32 pts, 27 km | 78 pts, **20 km** |
| crab | 56 pts, 64 km | 128 pts, **46 km** |
| giraffe | 31 pts, 34 km | 74 pts, **27 km** |

`n_min` measures sampling error, and a coarse polygon is long straight runs
meeting at sharp corners, which needs MORE samples to reproduce than a smooth
curve. So there is no distance argument for tracing coarsely, only a vertex cap.

Sixteen ship, floors 5.1 to 55.6 km. Octopus and bee were traced and dropped -
the arms tangle, the bee reads as a bird.

AND THE FLOOR IS NOT A SCORE. Half this log treats a lower floor as a win -
"more leaf-like AND less than half the ride", "the cheapest shape in the pack".
The rider it is being built for says a 3 to 8 km ride is too short. A floor is a
MINIMUM: a 5 km mushroom is still rideable at 50 km, so a low floor only widens
the choice, and it is the cheap end that needs justifying, not the expensive
end. The page's default distance goes 10 km to 30.

## 39. Traced beats hand-drawn in every pair that split, on one rater

First answers on the head-to-head. One rater, 22 items, no misidentifications
at all - all eight errors were "cannot tell", as in every round.

| arm | named |
|---|---|
| traced | 7/11 = 64% |
| hand-drawn | 4/8 = 50% |
| anchors | 3/3 |

The five matched pairs are the result, because they hold the subject, the
rater, the option list and the session fixed and vary only the drawing:

| subject | hand | traced | |
|---|---|---|---|
| butterfly | 0.102, cannot tell | 0.118, **named** | traced |
| crab | 0.132, cannot tell | 0.165, **named** | traced |
| maple | 0.062, cannot tell | 0.069, **named** | traced |
| giraffe | 0.058, named | 0.102, named | both |
| elephant | 0.066, cannot tell | 0.072, cannot tell | neither |

Three pairs split and all three went to the traced arm; zero went to the hand
arm. McNemar on three split pairs gives p = 0.250, which is the LOWEST p that
three matched pairs can produce - so this is the right direction at the
smallest sample that could show it, and not yet evidence.

THE SHARPEST LINE IN THE DATA is that in every split pair the traced arm won
with a WORSE shape distance. And at the extremes: a traced cactus at 0.300 over
71 km was named, while a hand-drawn elephant at 0.066 was not. A fit four and a
half times worse by the metric the entire search optimises, and it is the one a
person can name.

Also here, unremarked by the rater and worth noting: the bicycle was the one
route whose excursion broke the 0.08 limit (0.148, no placement qualified, the
search fell back), and it is one of the four traced routes not named. n = 1.

### 39a. Two raters: p = 0.016, and what it does and does not license

Seven matched pairs split and all seven went to the traced arm. McNemar exact
p = 0.016. Forty-four answers, and still not one misidentification - every
error in this project, across four rounds, has been "cannot tell".

| arm | named |
|---|---|
| traced | 14/22 = 64% |
| hand-drawn | 7/16 = 44% |
| anchors | 6/6 |

In every split pair the traced outline won with a WORSE shape distance, and at
the extremes a traced cactus at 0.300 over 71 km was named while a hand-drawn
elephant at 0.066 was not. That is the fourth and cleanest demonstration that
`shape_distance` is not a recognition scale.

SO THE FIVE LOSERS ARE RETIRED - butterfly, crab, giraffe, maple, elephant -
and `shapes.emoji` carries those subjects now.

WHAT IT DOES NOT LICENSE is retiring hand-drawing as such. The three hand-drawn
shapes in this round that were NOT in a pair - plane, music note, Christmas
tree - went 6/6. They are not worse than tracing; they were simply the ones I
got right.

AND TRACING IS NOT A RESCUE. Four traced routes went 0/4: turtle, whale,
elephant, bicycle. The first three are subjects whose silhouette is a blob with
one bump - the "one strange part" rule from BACKLOG 37 is about the SUBJECT, and
no amount of tracing fidelity gives a turtle a strange part. The bicycle is a
different fault: it is the one route whose excursion broke the 0.08 limit
(0.148, no placement qualified, the search fell back), so it is evidence for
the limit rather than against the tracing.

## 40. Per-point weighting: the cost was the wrong lever, the RADIUS is the right one

BACKLOG 33 said the plumbing was one line - `viterbi_closed_loop` multiplies
every emission by one global `snap_weight`, so a per-point weight is that
constant becoming an array. That was true and it did almost nothing. Weighted
against plain at the same placement:

| shape | plain | weighted (cost only) |
|---|---|---|
| e_elephant | 0.100 | 0.100 |
| cup | 0.124 | 0.124 |
| e_giraffe | 0.151 | 0.156 |
| gear | 0.124 | 0.126 |
| e_crab | 0.259 | 0.267 |

Two of five came out identical. The reason is that the DP had nothing to trade
with: candidates are the ten nearest junctions within 260 m, which on a 142 m
street grid is about two blocks, and re-pricing choices inside two blocks
changes which of them wins hardly at all.

FREEDOM IS THE LEVER, NOT PRICE. `build_candidate_sets` now takes a per-point
radius too: an identity-bearing arc gets 110 m and has to land close, a filler
arc gets up to 650 m and may take whatever street is convenient, with k raised
from 10 to 18 so a wider radius actually offers more nodes.

| shape | plain | weighted | excursion plain -> weighted |
|---|---|---|---|
| e_giraffe | 0.151 | **0.110** | 0.042 -> 0.048 |
| e_crab | 0.259 | **0.239** | 0.093 -> 0.095 |
| gear | 0.124 | **0.113** | 0.076 -> **0.064** |
| e_elephant | 0.100 | **0.093** | 0.042 -> 0.041 |
| cup | 0.124 | 0.129 | 0.100 -> **0.089** |

I PREDICTED THE OPPOSITE. BACKLOG 33 and the docstring both say a weighted
route must score WORSE on the unweighted metric, "by construction", because
holding the important arcs tighter costs error elsewhere. It improved shape
distance in four of five and excursion in three. The reasoning was wrong in a
specific way: loosening the filler arcs does not only trade against the fit, it
lets the DP find a better assignment overall, and the tight arcs cost little
because they were already being snapped closely.

Costs about twice the fit time (8s to 15s), from k = 18 rather than 10.

STILL NOT ON BY DEFAULT. Five shapes, one placement each, one city, and the
thing it is supposed to improve - whether a person can NAME the route - is not
what any of these numbers measure. A wider sweep first, then a rater round.

## 41. The emoji's interior lines: right idea, and the bitmap will not give them up

"The elephant would look much more like an elephant if the ear's outline were
drawn." Correct, and it generalises - an emoji's internal colour boundaries are
exactly the lines a person draws. Three attempts, none shipped:

  WHOLE COLOUR REGIONS, merged as contours. The dominant colour is the body, so
  including it traces a shrunken copy of the silhouette: a double outline, not
  an ear. Excluding it, the regions that clear an area floor are SHADOWS - the
  elephant's leg shading, the cat's foot - and they cost a great deal: elephant
  19.9 -> 41.7 km, cat 61.8 -> 97.3.

  THE EAR ITSELF is there, at 10.8% of the body, but split by anti-aliasing
  into three components of 3.6%, 1.2% and 3.5%. No single threshold picks the
  ear and rejects the shadows, and eroding the pieces far enough to keep their
  boundary off the silhouette deletes them.

  THE INTERIOR ARC - the part of the region's boundary that lies strictly
  inside the body, spliced in as an out-and-back stroke - is the right shape of
  answer and still crossed the closing segment. Fixable with more care about
  where the splice lands.

WHAT DOES WORK is transparent holes: the gear gets its bore back (13.3 km, and
CHEAPER than the 22.4 km hand-built one) and the cup gets the gap in its
handle. Two of twelve glyphs have one, because an emoji is an opaque picture
and most of its "holes" are painted.

THE REAL FIX IS NOT PIXELS. Twemoji (CC-BY 4.0) and OpenMoji (CC BY-SA) ship as
SVG, where the ear is a separate path and the line a person would draw is
available exactly rather than guessed from a 109 px bitmap. That also answers a
question this project has been ducking: the raters grew up on Apple's emoji and
the tracer uses Google's, so the POC 36 result - traced beats hand-drawn,
p = 0.016 - was won with the WRONG set, which makes it conservative.


## 42. The SVG tracer: the interior is read, not inferred

Item 41 ended with "the real fix is not pixels". `routeshape/shapes/openmoji.py`
is that fix. OpenMoji ships every emoji as SVG with the drawing separated the
way it was drawn - `<g id="color">` holds the filled regions, `<g id="line">`
holds the strokes - so an ear is a path and not a colour boundary guessed from
a 109 px render.

The three things the rider and the labellers asked for by name are now there:

    the gear's bore          21.0 km, a real ring rather than a painted circle
    the ghost's TWO eyes      7.9 -> 40.4 km
    the elephant's ear line  19.9 -> 26.4 km, one arc, no doubled outline

Four things had to be got right, and each of them was a bug first:

  ONE FIGURE IS MANY PATHS. Taking the largest filled path as the body gives a
  crab with no claws and a butterfly with no wings - 23 pt and 2.5 km of
  featureless blob. A path that sticks out of everything bigger is another
  PIECE of the silhouette and belongs in the union; a path wholly inside one is
  a DETAIL drawn on top and has to stay its own contour or the union eats it.
  Crab 23 -> 80 pt, butterfly 16 -> 52 pt.

  A FILLED PATH IS A REGION WHETHER OR NOT IT SAYS `z`. SVG closes a path to
  fill it. Asking `isclosed()` first threw away the sauropod's entire body,
  which OpenMoji draws as one unclosed filled path.

  SHADING IS THE SILHOUETTE REDRAWN. OpenMoji shades by filling a region
  bounded on one side by the outline itself - the snowman's two crescents, the
  house's door on the ground line. Kept as closed contours they retrace the
  outline a hair inside it and cross it wherever simplification moves either
  one: 28 crossings on the snowman, 28 on the mushroom. Cutting away the part
  that is within 1.2% of the boundary and keeping the rest as an open line
  gives the fold and the doorway and no crossings.

  THE SAME LINE TWICE. OpenMoji's fish has its gill arc in both layers, a few
  tenths of a percent apart; two copies of one curve cross at every wobble.
  Eight crossings, gone with a Hausdorff test.

And then a guard rather than a fix: features are added one at a time, longest
first, and a feature is kept only if the curve is still simple. A crossing is
fatal downstream - `describe.check` refuses the shape and no route is ever
built - and it is never worth losing the whole drawing to keep one line. All 28
subjects now trace with zero crossings.

WHAT IT DOES NOT DO is win everywhere, and that is the finding. Neither tracer
dominates:

    SVG better   elephant giraffe penguin turtle crab mushroom cactus anchor
                 guitar butterfly cat gear house fish cup
    bitmap better  maple apple bicycle rocket sauropod leaf music_note
                 christmas_tree snowman plane

The bitmap keeps the maple's points and the bicycle's spokes because those are
silhouette; the SVG loses the leaf's veins because OpenMoji's leaf has none.
So the shape library should hold the better DRAWING per subject, chosen by a
person, and POC 37 is what asks one.

The SVG cache (`_openmoji/`) is not tracked, on the same grounds as the OSM
extracts: it is refetched on demand. OpenMoji is CC BY-SA 4.0 and anything
published from these outlines owes it attribution.


## 43. Round four: Noto ties the hand-drawn pack, OpenMoji loses to it

Twelve subjects that exist as three drawings - hand-drawn, Noto-traced,
OpenMoji-traced - in front of two raters, 27 items each, each subject seen
twice and the tracer split six and six per rater.

    hand      19/24 = 79%
    Noto      10/12 = 83%
    OpenMoji   4/12 = 33%
    anchors     6/6 = 100%

    hand vs Noto      12 pairs, 0 split
    hand vs OpenMoji  12 pairs, 5 split, all hand, p = 0.062

POOLING THE TRACERS WAS THE WRONG TEST and it is what the analysis did first.
"Is hand better than emoji" pooled gives p = 0.062 too, but that number is just
a reading of how many OpenMoji items happened to be drawn. Split apart, the two
tracers are nowhere near each other and one of them is indistinguishable from
the thing it was supposed to beat.

SO POC 36's HEADLINE NEEDS NARROWING. "Traced beats hand-drawn, p = 0.016" was
measured on five subjects where what I drew was bad. On twelve subjects that
had already survived a rater round, tracing does not win - it ties. What POC 36
really showed is that tracing beats a BAD drawing, which is a claim about my
drawing and not about tracing.

AND THE SVG's EXTRA DETAIL IS A LIABILITY ON THE ROAD. The OpenMoji outlines
are plainly better to look at - the gear has a bore, the ghost has two eyes,
the house has a door - and they lost 5-0. The three that split are fish, house
and plane, and all three had GOOD excursion (0.032, 0.061, 0.052, limit 0.08).
Look at the routes and the mechanism is obvious: the interior detail is finer
than the street grid, so it survives in the outline and is ground off in the
route, leaving a polygon with no identity. Excursion does not catch this,
because excursion measures distance from the template and the template is the
problem.

    the one exception is the ghost, 2/2 on OpenMoji. The eyes work.

I tried to turn that mechanism into a number - smallest feature thickness over
street scale - and it does not work: an interior line is drawn out-and-back, so
its thickness is zero by construction and the metric reads the CONNECTORS, not
the features. The gear measured 7 m and was named by both raters. Recorded as
a dead end, not a signal.

WHAT SHIPPED. `server/app.py` now registers the sixteen emoji subjects with no
hand-drawn twin (Noto, not OpenMoji) and nothing else: one drawing per subject,
36 shapes on the page. Replacing a hand-drawn shape that ties is not an
improvement, and three cards reading 貓 is not a choice a rider can make.

STILL OPEN: leaf and snowman were named 0/4 across every arm and both raters.
Two raters is thin for a retirement, and a third is in progress.
