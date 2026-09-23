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

### 43a. Three raters settle it

    hand      28/36 = 78%
    Noto      15/18 = 83%
    OpenMoji   7/18 = 39%
    anchors     9/9 = 100%

    hand vs Noto      18 pairs, 1 split (Noto), p = 1.000
    hand vs OpenMoji  18 pairs, 7 splits, ALL hand, p = 0.016

So the call made on two raters holds and now has a p-value behind it: Noto is
indistinguishable from the hand-drawn pack, OpenMoji is worse than it at the
same threshold POC 36 claimed the opposite at. The ghost stays the one
exception - OpenMoji 3/3, and the hand-drawn ghost is also 3/3, so the eyes buy
nothing a rider would notice.

LEAF AND SNOWMAN ARE RETIRED. 0/6 each, across all three drawings and all three
raters - not "the traced one is better", nobody named any version. Same
evidence the crown went on. The pack is thirteen.


## 44. The recognition curve was fitted to the wrong thing; a lookup table beats it

`recognition.py` mapped `shape_distance` to a recognition rate and the service
reported the result as 「應該認得出來」. POC 39 pooled every judgement this
project has - 311 answers, 10 rater-sessions, 4 rounds, 62 drawings - and
fitted six models of it. AIC, and again on the 21 drawings with at least six
answers so a per-drawing rate is not fitting singletons exactly:

                            all 311     well-sampled 225
        none                  423.8        294.2
        distance              414.8        281.9     <- what shipped
        excursion             402.0        258.7
        distance + excursion  403.9        -
        drawing               305.8        190.5
        drawing + excursion   281.3        187.9     <- best

Three readings, in order of how much they cost:

  DISTANCE ADDS NOTHING once excursion is known. Same log-likelihood to two
  decimals, one more parameter, so `both` is strictly worse than `excursion`.
  The quantity the entire search minimises is not the quantity that decides
  whether a person can name the result.

  WHICH DRAWING IT IS BEATS ANY DISTANCE BY ~70 AIC. That is POC 32's
  permutation result arriving from another direction: a curve over a distance
  is a worse description of the data than a lookup table of what people said.

  EXCURSION STILL EARNS ITS PLACE on top of the drawing, 190.5 -> 187.9, at
  -49.7 log-odds per unit. +0.01 of excursion multiplies the odds of being
  named by 0.61 - within a shape, where the route strays matters.

SO THE LOOKUP TABLE SHIPS. `recognition.OBSERVED` is named/shown/mean-excursion
per drawing, and `rate()` smooths it (add a half, so 15/15 is not certainty and
0/6 is not impossibility) and adjusts for this route's excursion, clamped to
one log-odd because the slope is pooled and the adjustment is an extrapolation.
`verdict()` says it in counts - 「這個圖案給 13 個人看過，4 個認出來」- because
「約 92%」 from eleven answers and 「約 92%」 from a curve fitted to something
else read identically and are not the same claim.

A SHAPE WITH NO ROW NOW GETS NO NUMBER. The old code handed it the pooled
threshold; an average over a set this heterogeneous is not a weaker estimate,
it is another shape's answer. Five of the 34 on the page are unrated
(e_anchor, e_apple, e_guitar, e_rocket, e_sauropod) and say so.

TWO THINGS FELL OUT OF IT.

  The early stop was a fixed 0.97 recognition rate, which a measured rate
  cannot reach: 15/15 smoothed is 0.97 and thirteen answers never get near it
  however good the route. That was a test of how many people had seen the
  shape, not of the route. It is now `as_good_as_rated` - stop when this route
  strays no further than the routes that earned the shape its rate - and an
  unrated shape never stops early, which is the right way round.

  The page never showed the verdict AT ALL. The service has computed it since
  POC 29 and index.html never rendered it, so the one number a rider wants
  lived only in the JSON. It is now on the result card, and so is the fallback:
  when no placement met the limits the service still returns its best, which is
  deliberate and was silent. A 25 km gear now says 「這條多數人認不出來（這個
  圖案給 13 個人看過，4 個認出來）」 in red, which is true and was previously
  reported as 「應該認得出來」.

ALSO FIXED, and it would have been live: retiring the leaf and the snowman from
PACK promoted `e_leaf` and `e_snowman` to "subjects nobody drew by hand", which
would have put both straight back on the page. A retirement for being named by
nobody is about the SUBJECT; one for losing to the traced version is not, and
the elephant and the crab must keep their traced drawings. `NAMED_BY_NOBODY` is
the set the server excludes, not `RETIRED`.


## 45. Two corrections to 44, and what POC 38 finally said

### The recognition table was wrong an hour after it shipped

POC 39's first cut had two defects and both of them flattered it.

THE POOL WAS KEYED BY NAME AND FIVE SHAPES HAD BEEN REDRAWN under theirs. The
gear got its centre bore between round 33 and round 37 - the rider asked for it
- so "gear" was two different pictures pooled into one row, and the service
reported the current gear as 4 named of 13 when three of three raters named it.
The house (a door), the cup (a thicker handle), the butterfly and the leaf were
the same. `min_distance_km` is computed from the outline, so it fingerprints
the drawing: an answer now counts only if the shape's floor then equals its
floor now. 52 of 311 answers were about a picture that no longer exists.

HALF THE DRAWINGS WERE NAMED BY EVERYONE OR BY NOBODY, so the per-drawing model
separates the data perfectly and its coefficients ran to infinity - betas in
the thousands, under an AIC comparison built on a likelihood that can be driven
to zero. A ridge penalty makes every model estimable, and five-fold
cross-validation asks the question the product actually has: how well is the
NEXT answer predicted. Mean held-out log-loss per answer, 259 answers:

        none                 0.6598      the 16 drawings seen 6+ times: 0.5767
        distance             0.6560                                     0.5720
        excursion            0.6589                                     0.5753
        distance+excursion   0.6553                                     -
        drawing              0.5049                                     0.4328
        drawing+excursion    0.5052                                     0.4330

NEITHER DISTANCE NOR EXCURSION IS WORTH ANYTHING - all within 0.005 of knowing
nothing. The drawing cuts the loss by 23%. The -49.7 log-odds excursion slope
reported in 44 is WITHDRAWN: under the penalty it is 0.0, and the per-route
adjustment is gone from `recognition.rate`.

`as_good_as_rated` stays, but as what it is: a stopping rule, not a claim that
the route will read. It still took a 25 km gear from 20 seconds to 6.

The gingerbread man is retired, 0/6, on the rule the leaf and the snowman went
on. Twelve hand-drawn shapes; 33 on the page; six never rated.

### POC 38 finished, and per-point weighting works exactly as designed

36 fits across four container reclamations (the resume was worth writing).
Averages over six shapes, one placement each:

        arm       salient   filler    exc    dist
        base         29.7     31.1   0.061   0.114     k = 10
        wide         32.0     33.7   0.058   0.111     k = 18, nothing else
        radius       32.0     33.7   0.058   0.111     per-point radius
        full         29.8     33.6   0.059   0.116     + per-point cost
        tight        28.3     33.7   0.060   0.121     75 m on salient points
        sharp        26.5     34.5   0.060   0.128     contrast 8

THE MECHANISM IS REAL AND MONOTONE. `sharp` takes the identity-bearing quarter
of the contour from 32.0 m to 26.5 m and pays for it exactly where the design
said it would - filler 33.7 -> 34.5, shape distance 0.111 -> 0.128. On the gear
it is 42 m -> 24 m. The idea works.

AND TWO THINGS IT KILLED ALONG THE WAY. `radius` came out IDENTICAL to `wide`
on all six shapes: a candidate set is the k nearest junctions WITHIN the
radius, so widening past the k-th nearest changes nothing, and 150 m over a
280 m grid never reaches the tight end. BACKLOG 40's "the radius is the lever"
is wrong. What moved those routes was k going from 10 to 18 - and it moves them
the WRONG WAY: k = 18 takes the gear's salient quarter from 35 m to 42 m while
improving filler, excursion and distance, because more candidates let the DP
push error onto the arcs that carry the identity, where it is cheap.

IT STILL DOES NOT SHIP, and the reason is POC 39 rather than anything here.
Weighting spends search effort moving the route WITHIN a shape, and every
route-level quantity just measured worse than knowing nothing at predicting
whether a person names the result. Turning it on would need a rater round to
prove the 5.5 m is visible, and on the evidence the round would come back null.
Shelved with the measurement, not with a shrug.


## 46. The resolution floor does not predict anything, and it takes a story with it

I proposed this one as the single thing worth building: a scale-space measure
of how much of a drawing lives below the resolution a street network can hold.
`legibility.resolution_error` resamples the template at one point per street
and reports the worst gap as a fraction of width - a FLOOR on excursion that
needs no network and no fitting, computable before anything is ridden.

It predicts nothing.

    per answer, mean held-out log-loss   none        0.6598
                                         distance    0.6560
                                         excursion   0.6589
                                         resolution  0.6598   <- exactly the null
                                         drawing     0.5049

    per drawing, 28 seen 3+ times        Spearman +0.057, p = 0.772

The table says why at a glance. The snowman, named by nobody in nine showings,
has one of the LOWEST floors (0.0125); the plane, named by all fifteen, has one
of the highest (0.0247). The heart (11/11) and the cat's head (0/4) sit two
rows apart at the bottom. What the measure actually ranks is how wiggly an
outline is, and wiggliness has nothing to do with whether a person can name the
subject.

AND IT WITHDRAWS THE MECHANISM I HAD BEEN ASSERTING SINCE BACKLOG 43. The story
for OpenMoji's three losses was "the interior detail is finer than the street
grid, so it survives in the outline and is ground off in the route". The floors
say otherwise:

    house    0.0269   3/3          o_house   0.0282   0/1
    plane    0.0247  15/15         o_plane   0.0283   1/2

Indistinguishable. Whatever beat the OpenMoji drawings, it was not resolution.
That explanation is withdrawn; the observation (they lost, p = 0.016) stands
and is now unexplained.

THE USEFUL PART IS THE ABSOLUTE NUMBERS. Every drawing in the library floors
between 0.009 and 0.041 of its width, against an excursion limit of 0.08. At
the sizes people actually ride, THE STREET NETWORK IS NOT THE BOTTLENECK - it
can resolve everything we draw, twice over. That is consistent with POC 39
finding the drawing worth 23% of log-loss and every route-level measure worth
nothing: the limit on being recognised is the picture, not the map.

The module is kept. `vanishing` still says which arc of a drawing the scale
cannot hold, which is the right diagnostic for the day a shape IS too fine for
a city - Taipei at 25 km is simply not that day.


## 47. Round five: every shape on the page now has a number

Sixteen traced subjects and three anchors, one rater so far. Anchors 3/3, so
the round is sound. Traced 10/16.

Folded into the pool - 278 answers, 11 rater-sessions, 5 rounds - the model
comparison is unchanged and slightly sharper:

        none 0.6628   distance 0.6589   excursion 0.6619   drawing 0.5019

THE CACTUS DID IT AGAIN. Named, at shape distance 0.300 and excursion 0.091 -
over the limit the service enforces. That is the second rater in two rounds
naming a route both of our metrics call unusable, and it is now 3/3. If one
observation had to carry the whole argument of the last two days, it is this
one.

WHERE THE SIXTEEN STAND, pooled over POC 36 and 41:

    3/3   crab  giraffe  penguin  maple  cactus  butterfly
    2/3   mushroom
    1/3   whale
    1/1   anchor  guitar  sauropod
    0/3   elephant  turtle
    0/1   apple  rocket  bicycle

The elephant is the one to sit with. It was the shape POC 35 traced to rescue -
the hand-drawn one was retired for losing to it - and three raters in two
rounds have now failed to name either version. Tracing did not save that
subject; it only made the losing version different.

`recognition.OBSERVED` has 33 rows and the page has no unrated shapes left. Six
of those rows rest on one answer, which is why the wording carries the counts:
「這個圖案給 1 個人看過，1 個認出來」 cannot be mistaken for a rate.

### 47a. Second rater, and two subjects are close to done

Anchors 6/6. Traced 21/32. Pooled over POC 36 and 41:

    4/4   crab  giraffe  penguin  maple  cactus  butterfly
    3/4   mushroom
    2/2   anchor  guitar  sauropod
    1/4   whale
    1/2   rocket
    0/2   apple  bicycle
    0/4   elephant  turtle

The elephant and the turtle are at 0/4. The retirement rule this project has
used three times is "named by nobody over at least six showings", so neither
qualifies yet - but the elephant is the shape POC 35 traced specifically to
rescue, and the version that beat it was retired for losing. Two more raters
decide it.

297 answers now. The comparison has not moved: drawing 0.4949, distance 0.6577,
excursion 0.6606, knowing nothing 0.6614.

### 47b. Third rater, and the elephant is retired

Anchors 9/9 across three raters - the round is sound. Traced 32/48. 316 answers
in the pool now; the comparison has not moved in five rounds:

    drawing 0.4850   distance 0.6465   excursion 0.6495   knowing nothing 0.6502

Where the sixteen traced subjects land:

    5/5   crab  giraffe  penguin  maple  cactus  butterfly
    4/5   mushroom
    3/3   anchor  guitar
    2/3   rocket  sauropod
    1/3   apple
    1/5   whale
    0/3   bicycle
    0/5   turtle
    0/5   elephant   (and 0/2 hand-drawn: the SUBJECT is 0/7)

THE ELEPHANT IS RETIRED and it is the expensive admission of this project. POC
35 traced it BECAUSE my drawing was failing, and POC 36 retired my drawing for
losing to the traced one - a result at p = 0.016. Five rounds later the subject
is 0 of 7 across both drawings. What POC 36 measured was not "tracing wins", it
was which of two unrecognisable elephants a rater preferred to say nothing
about. A significant difference between two failures is still two failures.

`elephant` is in both BEATEN_BY_TRACING and NAMED_BY_NOBODY, and the server
reads the second, so the subject cannot come back through its traced twin.

NOT RETIRED, and said plainly rather than decided quietly: the turtle at 0/5
and the bicycle at 0/3 are short of the "nobody, over at least six showings"
rule that the leaf, the snowman, the gingerbread man and now the elephant went
on. They stay on the page carrying their own counts, which is what the counts
are for. The rider has said there are no more raters, so they stay at 0/5 and
0/3 unless someone decides otherwise - one showing short is not the same as
failing, and the page does not pretend it is.

32 shapes.


## 48. Withdrawn on a product call, dead code out, and a hypothesis worth a round

### Six subjects leave the page

    cat 3/13   witch_hat 2/6   turtle 0/5   bicycle 0/3   whale 1/5   apple 1/3

Named by fewer than half the people who saw them. This is a product call and
not the retirement rule: the turtle and the bicycle are short of six showings,
and the honest label on the card was already there. The label does not help -
it only means the disappointment was disclosed before the ride rather than
after it.

The cat is the one that stings. Three redraws across this project, a rater who
read the first one as Pikachu, a body-and-tail rebuild, and 3 of 13.

`pack.WITHDRAWN_SUBJECTS` is what the server reads now, and it is the union of
NAMED_BY_NOBODY (the rule) and BELOW_HALF (the call). The two sets stay
separate so which one a subject left under is still visible. 26 shapes.

### Dead code

`EARLY_STOP_RECOGNITION` had not been read since `as_good_as_rated` replaced
it. The distance curve above it in recognition.py stays, because POC 30's fits
quote it and rewriting history is worse than a labelled fossil.

### The rider's hypothesis about OpenMoji, and how to test it

Why OpenMoji lost 5-0 has been unexplained since POC 40 withdrew my "too fine
for the street grid" story. The rider's reading: OpenMoji is drawn in COLOUR,
and a route is a LINE, so its geometry is built for something we cannot use.

That is testable and cheap, because OpenMoji ships both:

    color/svg/1F418.svg   4368 bytes, 2 fills, 5 strokes
    black/svg/1F418.svg   1880 bytes, 0 fills, 5 strokes

The black variant is PURE STROKE - no filled regions at all. If the hypothesis
is right, tracing `black/` should beat tracing `color/`, because the drawing is
already the thing a route can be. `shapes.openmoji` needs only its SOURCE url
changed and its filled-path branch made optional to try it.

WHAT WOULD MAKE IT A FAIR TEST and not another round of my own taste: the same
instrument as POC 37 - the same subjects, one arm per rater, blind. The honest
prior is poor, because POC 39 says no property of the route predicts naming and
this is a claim about the drawing, which is the one place the data says to look.


## 49. The search is deterministic and was being run twice

Asking for the same route twice returned a byte-identical answer and spent the
full search arriving at it again: 24.5 km, shape distance 0.166, rotation 60,
6.6 seconds - twice. The coarse scan ranks a fixed grid, `select_candidates`
takes the top few and the Viterbi has no random component, so there was never
anything to recompute. A fish at 30 km spends 53 seconds on it.

`build_route` is now cached on `(shape, target_km, mode, lat, lon)`, with
latitude and longitude rounded to four places - about 11 m, and a placement
grid stepped in hundreds of metres cannot tell two points that close apart.
Repeat requests come back in milliseconds carrying the same route id, so the
GPX link they point at is the same file rather than a second copy of it.

`force` was already accepted by the endpoint and ignored - a leftover from a
gate POC 29 removed. It now means what its name says: skip the cache and
replace the entry. Since the search is deterministic it returns the same route,
so it is a tool for after a code change, not something the page needs a button
for.

TWO THINGS THE CACHE HAD TO NOT BREAK, both checked:

  The reply is a COPY, so a caller mutating it cannot poison the entry, and
  `seconds` is overwritten with what THIS request cost. Reporting the original
  53 seconds for a reply that took a millisecond would be a lie in the one
  field whose whole job is to say how long the work took. The page prints
  「之前算過了」 rather than 0.0 s.

  The cache never expires, and that is safe only because `ROUTES` - which holds
  the GPX each answer links to - also lives for the life of the process. A
  cache outliving its GPX would hand out a download link that 404s. Verified:
  a cached id still downloads 67 KB.

WHAT THIS IS NOT. It does not make a FIRST request faster, and the rider's own
suggestion - serve a nearby distance from a precomputed set - is still open.
That one needs a product decision first: `width_m` comes from `target_km`, so
answering a 28 km request with a 30 km route means the rider rides 30. Worth
doing, and worth saying on the page when it happens.


## 50. Type a word, get a shape - 1,266 of them, offline

The shape list was 26 drawings, and a rider who wanted a castle had no way to
ask for one. `shapes.emoji`'s tracer was never tied to its PACK - it takes any
character the font has a glyph for - so what was missing was only the step from
a typed word to that character.

THE WORDS COME FROM UNICODE'S OWN CLDR ANNOTATIONS, Traditional Chinese and
English, not from a table I wrote. That is the difference between a feature and
a demo: a hand-written list of a hundred nouns covers whatever I happened to
think of. 狗 finds 🐕 before 🐶 and 🌭; 恐龍 finds 🦖 and 🦕; a pasted emoji
outranks every word match.

THE INDEX IS BUILT, NOT FETCHED. Every candidate has to survive the whole
pipeline at build time - the font has the glyph, the tracer produces a curve,
`describe.check` passes it, `feasibility` can size it - and only then does it
get a row. 1,266 in, 27 refused, 216 KB committed. A rider typing 狗 cannot
reach a crash and does not need the network.

TWO PATHS, AND THIS IS THE OTHER ONE. `/api/describe` asks a model to invent an
outline; it needs credentials and returns a drawing nothing has checked. This
searches pictures that already passed. They are complementary and the model one
is left alone.

WHAT THE UI HAD TO SAY, and the reason this is not just a bigger dropdown: the
26 built-ins carry rater counts and these carry none. Every hit says 「還沒有人
看過」 on its own card, and the route comes back 「還沒有人看過這個圖案，不知道
認不認得出來」. POC 39 found the drawing is the only thing that predicts naming,
so widening what can be ASKED for is not widening what is known to work, and
the page must not let the two look alike.

The request sends the EMOJI, not the `q_1F3F0` the search registered it under.
That name lives in the server's memory; a restart between searching and pressing
the button would turn it into "unknown shape", while the character always
resolves. 🏰 at 25 km: 24.5 km, distance 0.098, excursion 0.072, 40 seconds.


## 51. Routes that survive a restart

The in-memory cache made a repeat instant and lost everything when the process
ended, so the first rider after every restart paid 8 to 53 seconds again for a
route the server had already found.

WHAT IS STORED IS THE ROUTE, NOT THE PICTURE, and the measurement is the whole
design. One answer is 1,068 KB and 1,045 of them are `streets` - the 16,433
road polylines the page draws behind the route. Those are a bounding-box filter
over the network, so they are rebuilt on the way out and never written down.
What is left is 22 KB: at 1,500 routes, 33 MB instead of 1.6 GB.

The GPX is rebuilt the same way, from the route's own WGS84 coordinates, so a
restored route needs no projection and no graph to hand out a download.

SQLITE FROM THE STANDARD LIBRARY. Nothing to install for something a person has
to run in one command, one file to delete when it goes wrong, and it is what
this actually is - a key-value store that must outlive a process and be
inspectable when a route comes out wrong.

THE FINGERPRINT IS THE PART THAT EARNS ITS KEEP. A stored route is valid only
while the shape still means what it meant, and this project has already been
bitten hard by exactly that: the gear got its centre bore between two rounds,
five shapes were redrawn under their own names, and the rater pool was quietly
wrong for weeks until BACKLOG 45 found it. So every row carries a hash of the
outline it was fitted to, and a row whose shape no longer hashes the same is
deleted at load rather than served. Verified by forging a hash: the gear's row
is dropped, the fish's survives.

    restart -> 1 routes restored from _routes.db
    same request -> 0.0 s, cached, same id, 16,433 streets, 54 KB of GPX

`--precompute` fits every shape at the four preset distances and fills the
database; `--no-store` runs without it. The database is not tracked - it is
rebuilt on demand, like the OSM extracts and the OpenMoji cache.

STILL NOT DONE, and it is the rider's original suggestion: serving a NEARBY
distance from a precomputed one. That needs a product decision first, because
`width_m` comes from `target_km` - answering a 28 km request with a 30 km route
means the rider rides 30, and the page would have to say so.


## 52. 「換一個位置」, and two bugs that made it a button that did nothing

A rider who looks at a route and says 「不像」 needs something to press, and
「重新產生」 cannot be it: the search has no random component, so the same
request returns the same route to the byte. What they actually want is the same
shape drawn SOMEWHERE ELSE, and the search already fits several placements and
keeps the best - so the runners-up are the feature.

`variant` is that. It joins the cache key, so each placement is stored and
re-served like any other route, and `more` says how many are left.

TWO BUGS, BOTH FOUND BY LOOKING AT THE COORDINATES RATHER THAN THE SUMMARY.
Variant 1 of the gear came back 24.5 km at distance 0.166 - exactly variant 0 -
twice over, for two different reasons:

  TWO PLACEMENTS CAN FIT THE SAME ROUTE. `select_candidates` keeps its centres
  MIN_SEPARATION_M apart, but centres that far apart still snap onto the same
  junctions. Deduplicated on the route now, not on the placement.

  THE TWO RUNS RANKED DIFFERENT SETS. Variant 0 stops early at the first good
  placement; variant 1 searches all six. The gear's second-best out of six was
  the one the early stop had already returned. So a variant now also excludes
  whatever the lower variants of the same request handed back, which the cache
  is holding anyway.

AND THE COUNT HAD TO BE HONEST ABOUT NOT KNOWING. Variant 0 stops early, so it
cannot say how many alternatives exist - and reporting the 0 it can see hid the
button from every rider whose first answer was good, which is most of them. It
reports the candidates not yet tried, and the page drops the number in that
case rather than promising routes that may not exist:

    first       換一個位置
    after one   換一個位置（還有 1 個）
    after two   hidden - there were three, all seen

### 51a. The database, filled

`--precompute` fitted every shape at every preset distance it can reach:

    75 routes fitted, 78 in the database (three are 25 km, from testing)
      10 km   5      30 km  22      50 km  24      100 km  24

    slowest: e_giraffe 100 km (265 s), gear 100 km (260 s), bat 100 km (260 s)

And on a cold server the answers are immediate:

    78 routes restored from _routes.db
    gear 30 km -> 29.2 km in 0.0 s, cached

TWO DO NOT FIT AT 100 KM and come back 「no route」 - e_penguin and taiwan. Only
successes are stored, so every future precompute spends about six minutes
rediscovering that. Left alone rather than caching the failure: a route that
cannot be placed today may be placeable once the network grows, and a stored
「no」 would hide that.

THE RUN WAS KILLED HALFWAY by a container reclamation, which is the second time
this session, and it restarted from route 77 of 77 without recomputing the 76
before it. That is the resume working for the reason it was written.


## 53. --precompute spent its time downloading the same city twenty times

The rider ran it and watched it sit. The fits were not the problem:

    loaded bike network ... in 323.5s
    loaded bike network ... in 181.1s
    loaded bike network ... in 138.5s
    loaded bike network ... in 122.5s        ... and so on, twenty-odd times

THE HALF-SIZE COMES FROM THE SHAPE'S WIDTH, so every job asked for a slightly
different box - 8460, 9052, 9997, 10858, 13106 m - and `_networks` keyed on the
exact number, so each one was a fresh download of the same city. Then Overpass
refused a connection, the fallback tiler got a 509 after 208 of 700 tiles, and
the run died with a traceback 40 jobs short.

TWO FIXES, AND THE FIRST ONE IS FREE. A box already loaded that CONTAINS the
request will do, because the placement grid's margin comes from the shape's
half-size and not from the network's - so the same centres are scanned either
way. The only difference is that a route near the edge of that grid can follow
a street that used to be outside the downloaded box, which is more of the city
rather than less. With `--precompute` now fitting largest first, the widest
shape downloads the widest box and the other 76 jobs reuse it: twenty-odd
downloads become one, measured at 104.9 s for 78,330 nodes.

And one job's failure is no longer the run's. Each fit is caught, named, and
the run continues; the failures are listed at the end to retry, which the
resume already makes cheap.

WHAT THIS DOES NOT FIX is the first request on a cold machine, which still
downloads whatever box the biggest shape needs. That is the network, not us.

### 53a. The whole run, after the fix

    77 fitted, 0 failed, 76 in the database (3.8 MB)
    3 network downloads, 74 reuses - 105 s, 99 s, 97 s
    152 minutes of fitting; slowest bat 100 km (303 s)

THREE DOWNLOADS, NOT ONE, and that is correct: a loaded box is reused only by
requests it CONTAINS, so a shape needing a wider one still pays. Largest-first
gets that down to the handful of times the widest requirement grows. The rider's
previous run paid twenty-odd.

The one route not in the database is `e_penguin` at 100 km - 「no route」 rather
than a failure, and only successes are stored, so it will be retried by any
future run. BACKLOG 51a already explains why a "no" is not cached.

A cold server restores all 76 and answers from them immediately:

    gear   30 km -> 29.2 km in 0.0 s     trex  50 km -> 43.9 km in 0.0 s
    e_crab 50 km -> infeasible           (its floor is 52.2 km; correct)


## 54. The inner loop is networkx, and that is the whole cost

The rider asked why `--precompute` cannot be parallelised, and the answer turned
out to be that parallelising it is solving the wrong problem.

WHAT ONE ROUTE DOES. `plan` sizes the shape, `coarse_scan` slides it over a grid
of centres times twelve rotations, `select_candidates` keeps six well-separated
placements, and each placement then runs the matcher: ten candidate junctions
per contour point, a Dijkstra from every candidate of step i to reach the
candidates of step i+1, and a Viterbi over the closed loop. Sixty contour points
times ten sources times six placements is 3,600 Dijkstras for one route.

MEASURED, one placement's transition costs on a 55,215-node network:

    total                       12.58 s
      nx.single_source_dijkstra  9.85 s   78%
      _path_deviation            2.62 s   21%   (route_to_xy 1.75 s of it)

AND THE SAME DIJKSTRAS IN SCIPY:

    networkx, 10 sources, 3 km cutoff   0.22 s   (22 ms each)
    scipy.sparse.csgraph, all 10 at once 0.01 s   ( 1 ms each)   33x
    the CSR arrays                       2 MB    (the graph: ~1,500 MB)

WHY FORK AND COPY-ON-WRITE DO NOT SOLVE IT. Sharing a networkx graph between
processes sounds free and is not: CPython's reference counting WRITES to an
object's header when you READ it, so a child traversing the graph dirties the
pages it touches and copy-on-write copies them. A networkx graph is millions of
small dicts, so a worker ends up with most of the 1.5 GB anyway. `gc.freeze()`
stops the collector writing but not the refcounts. What genuinely shares is a
numpy array - one object, one buffer, no refcount traffic per element - which
is exactly what the CSR form is.

SO THE ORDER OF WORK IS: make it fast, then parallelism is nearly free, because
`scipy.sparse.csgraph.dijkstra` releases the GIL and threads would do.

    1  Build the CSR once per network, beside the graph in `_networks`. Node id
       to index, edge lengths as the weights. The graph is a MultiDiGraph, so
       take the shortest parallel edge per (u, v) and remember WHICH key won -
       the geometry has to come from the same edge the cost came from. Keep it
       directed; one-way streets matter to a bicycle.

    2  Batch the step's sources. `dijkstra(csr, indices=[...], limit=cutoff,
       return_predecessors=True)` does all ten in one C call.

    3  Rebuild the paths from the predecessor matrix. A pure-Python walk back
       from v to s, but only over a path's own nodes and only for the hundred
       (u, v) pairs a step has - trivial next to the search it replaces.

    4  THEN `_path_deviation` is 90% of what is left, so precompute each edge's
       densified geometry once per network and make `route_to_xy` a
       concatenation instead of a per-call rebuild.

HONEST ARITHMETIC, AND THE FIRST VERSION OF THIS PARAGRAPH WAS WRONG. Steps 1-3
take that 9.85 s to about 0.3 and the whole STEP to ~2.9 s, and with step 4
perhaps 0.8 - 10 to 15x on the step. I then wrote that 152 minutes of
precompute would become 10 to 15, which is the step's ratio applied to the
whole request. It is not the whole request.

Profiled end to end, one online route (gear, 30 km, 18.7 s under the profiler):

    refine                      14.3 s   77%
      compute_transition_costs   9.5 s   51%
        nx dijkstra              6.5 s   35%   <- changed by this work
        _path_deviation          2.9 s   16%   <- changed by this work
      build_candidate_sets       4.8 s   25%   <- not touched
    streets_near                 3.4 s   18%   <- not touched

Dijkstra is 35% of a REQUEST, not 78%. Removing it gives 1.5x; removing the
deviation cost as well gives about 1.9x. So roughly 2x online and 2x on
precompute - 152 minutes to about 80, not to 15.

The exception is the long routes. A 100 km shape does not stop early, so all
six placements run and transition costs take a larger share; that batch should
see 2.5-3x. And `build_candidate_sets` at 25% is the next thing worth reading
if speed ever matters more than it does now - though it is already numpy and
scipy, so there is no cheap win waiting there.

HOW TO KNOW IT IS STILL CORRECT, and this is the part worth the most: the route
store already holds 76 fitted routes with a fingerprint of the outline each was
fitted to. Re-fit them after the change and every coordinate must match. The
database written to make the demo fast is a regression suite nobody had to
build.

Not done. The demo comes first, and this is an offline step that runs once.

## 55. The street background was clipped to 4,500 m on every restored route

A route restored from `_routes.db` has no street background stored with it -
`streets` is 1,045 KB of the 1,068 KB answer, so it is rebuilt on the way out
(BACKLOG 48). `_rehydrate` asked `network()` for the default 4,500 m box to
rebuild it from, whatever the length of the route.

Measured over the 76 rows in the store: a 100 km route reaches 7.0 km from the
centre and the widest reaches 13.1 km. **43 of 76 stored routes** - every
50 km and 100 km one - came back with the map ending part-way along the route
and the rest of the line floating on blank page. In a single process it never
showed: the fit had already loaded a box the shape's own width and the reuse
rule in `network` served it. It appears only after a restart, which is exactly
when the store is what answers - so precomputing made it universal.

Two changes:

- `_street_half_size_m(answer)` sizes the box from the route's own extent plus
  the `streets_near` pad, so the background covers the route it belongs to.
  Measured on the 100 km bat: background 5,593 m before, 8,972 m after, route
  7,031 m.
- `cached_covering()` gives the on-disk cache the rule the in-memory cache
  already had - a larger box for the same centre and mode contains this one, so
  load it instead of downloading. Without it the fix would have been worse than
  the bug: every restored route asks for a size no cache file is named after
  (7,431 m, 8,462 m, 10,926 m) and would have downloaded a network to draw a
  map behind a route already computed.

`--warm` now loads the box the widest stored route needs rather than the
default one, so the cost is one load at startup instead of a stall on the first
100 km click.

## 56. The route mark was a salted hash, so every stored one was dead

Found by refactoring, not by looking. `_build_route_uncached` was 218 lines, so
the ranking and de-duplication were pulled out into `rank_fits`. To prove the
extraction changed nothing, four real routes were fitted before and after and
the answers hashed. Every hash differed - while every number in them was
identical.

The difference was `mark`, and the cause is that it was
`str(hash(route_xy.tobytes()))`. **Python salts the hash of bytes with
PYTHONHASHSEED, which is random per process.** The mark is written to
`_routes.db` and compared, on the next start, against a freshly computed one.
All 76 precomputed routes carried a mark that could never match anything.

So the exclusion in `rank_fits` - the thing that stops 「換一個」 handing back
the route just rejected - silently stopped excluding after every restart. It
worked in the process that computed the route and nowhere else, which since
precompute is every session a rider sees. BACKLOG 51 fixed this bug once
already, in a different form; this is the same button failing again, for a
reason no page inspection could have shown.

Two fixes were possible and only one of them is a fix. A stable digest of the
projected geometry corrects the next route and leaves those 76 broken, because
nothing in a stored row can reproduce projected metres. The mark is therefore
taken off the **WGS84 coordinates**, which is what the row already holds: an
old row's mark is now computed from the row rather than trusted, so there is
nothing to migrate and the existing database heals on load.

`rank_fits` and `admissible_fits` are testable without a map now, which the
ranking never was. 18 tests, one of which spawns three processes and asserts
the same route marks the same in all of them - it fails against the old
implementation with three different marks.

The refactor itself was proved inert: same route_km, same shape distance, same
everything but the mark, on four fits across two shapes, two distances and two
variants.

## 57. `streets_near` walks every edge, so the map costs more than the route

Measured serving one stored 30 km heart, whose route reaches 3.6 km from the
centre:

    4,500 m box    58,396 edges    2.31 s    36,501 polylines
    13,453 m box  187,037 edges    4.89 s    36,503 polylines

The same map, 2.1x the time. `streets_near` iterates `graph.edges(data=True)`
and rejects each edge by bounding box in Python, so the cost follows the size
of the NETWORK rather than the size of the route - and a cached route, which
does no fitting at all, spends its entire latency here.

Found by warming the widest box the stored routes need (BACKLOG 55) and
watching a cached click go from instant to 6.8 seconds. The immediate fix is
to warm the default box as well and let the reuse rule hand each route the
smallest box that contains it, which puts short routes back on the fast path.
That is a workaround: a 100 km route still pays 4.89 s for its background, and
so does any route in a city where the only loaded network is large.

The real fix is an index. Per network, once: an (n_edges, 4) array of edge
bounding boxes and the edge geometries, so selection is a vectorised numpy
comparison and only the surviving edges are transformed to WGS84 - the
per-edge `Transformer` work is the other half of the cost. Same shape of
change as BACKLOG 54's precomputed edge geometry, and the two share the array.

Worth pairing with 54 rather than doing alone: after 54 removes 35% of a fresh
request, this is what is left of a cached one.

### What a cached route actually costs, measured over HTTP

With both boxes warm and the route already in the store, so no fitting at all:

    triangle  10 km    1.45 s    0.81 MB     12,675 polylines
    heart     30 km    2.69 s    2.61 MB     36,501 polylines
    heart    100 km   10.36 s    8.74 MB    112,073 polylines

All of it is the street background: rebuilding it, serialising it, and sending
it. `seconds` reports 0.0 for these, which is true of the FITTING and is the
only part it was ever measuring.

BACKLOG 55 is why the 100 km figure is what it is. Before it, a restored 100 km
route was served out of the default 4,500 m box, so `streets_near` had far less
to filter and far less to send - it was faster because the map stopped
part-way along the route. Correct and slow is the right trade of the two, but
10 seconds and 8.7 MB for the shapes that are most worth showing is not where
this should end.

### Where the 10 seconds actually go

Measured end to end in a real browser (Playwright, Chromium), cached 100 km
heart, both networks warm:

    fetch (server + transfer)   8,332 ms    85%
    innerHTML + layout          1,176 ms    12%
    build the SVG string          235 ms     2%
    JSON.parse                     73 ms     1%

**The browser is not the problem.** 112,073 `<path>` elements cost 1.4 s
between them, and the fear that the page was the bottleneck was wrong. Almost
all of it is `streets_near`, which is 8.82 s of the 9.19 s the server spends.

Inside `streets_near`, over the same 171,430 edges:

    walk and bbox-reject, no transform    3.33 s    42%
    ...plus transform + build the lists   7.97 s    (so survivors cost 4.64 s, 58%)

111,993 of 171,430 edges survive the bbox test - 65%. So **indexing the
rejection, which is what this entry proposed, addresses 42% at best.** The
larger half is the survivors: one `Transformer.transform` call per edge, and
one Python list comprehension per edge to round the coordinates.

Both halves are per-edge Python where a batch would do:

  - Precompute an (n_edges, 4) bounding-box array per network, once. The filter
    becomes a numpy comparison and the 3.33 s goes with it.
  - Concatenate the survivors' coordinates and transform them in ONE pyproj
    call, then split them back. pyproj's per-call overhead is most of what
    111,993 calls cost.

NOT YET SPLIT, and it decides how much the second bullet is worth: of that
4.64 s, how much is pyproj and how much is `[[round(a, 5), round(b, 5)] for
...]` over 112,000 polylines? If it is mostly the list building, batching the
transform will disappoint and the answer is to send fewer polylines instead.
That is a five-minute measurement and it should be the first thing the work
does - the same measurement, skipped, is what made BACKLOG 54's estimate wrong
by a factor of six.

### Quantising the box sizes - DONE

`_street_half_size_m` now rounds up to 1 km steps and `--warm` loads the
default, the median and the widest, rather than only the two extremes. The 79
stored routes went from 48 distinct half-sizes to 11:

    4500 m  31 routes     5000  5     6000  12     7000  6     8000  9
    9000 m   5 routes    10000  4    11000   4    12000  1    13000  1
   14000 m   1 route

**48 of the 79 are now served by a box of 6,000 m or less**, where before every
one of them fell through to the widest loaded box.

How much that buys depends on how much smaller the box is, and the honest
answer is less than the first measurement suggested:

    30 km heart    4,500 m box   58,396 edges   2.31 s  |  13,453 m  187,037   4.89 s   2.1x
    100 km e_crab  6,000 m box   88,639 edges   4.28 s  |  14,000 m  190,190   5.69 s   1.3x

Both produce the identical map - 36,501 and 46,670 polylines respectively,
whichever box is used - and that is the reason for the gap. **The survivors are
the same either way.** Every extra edge a larger box carries is rejected, and
rejection is the cheap half: about 19 microseconds an edge, against the
41 microseconds each survivor costs to transform and serialise.

So quantising can only ever recover the rejection work, which is 42% of
`streets_near`. It is worth having - it is nearly free and it stops the stitch
cache thrashing - but it is not the fix. The 58% below is.

Quantising alone would have changed nothing, and that is the part worth
remembering: the reuse rule serves a request from the smallest LOADED box that
contains it, so unless the warmed set sits on the buckets, a route asking for
5,000 m still gets handed the 14,000 m network. The two halves only work
together.

Still outstanding below, and still the larger half.

A fourth lever, independent of both: **the box sizes are not quantised.** The 78
stored routes ask for 48 DISTINCT half-sizes (4500, 4514, 4547, 4629, ...,
13453), because `_street_half_size_m` returns a route's exact reach. Two
consequences. On disk each size is its own ~70 s stitch and the 400 MB budget
evicts the others, so the cache thrashes. In memory `--warm` loads 4,500 and
13,453, and every route between them falls through to the larger - which is
exactly the slow path warming both boxes was meant to avoid. Rounding up to
1 km steps collapses 48 sizes to about 10, makes stitches reusable, and hands a
route reaching 4.7 km a 5,000 m box (~65,000 edges) instead of a 13,453 m one
(171,430). Cheapest of the three by a wide margin.
