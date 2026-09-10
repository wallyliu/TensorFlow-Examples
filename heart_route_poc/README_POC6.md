# POC 6 — Beyond hearts, and a second rater

Two things POC 5 left owing: the pipeline had only ever been run on one shape,
and its entire conclusion rested on eight judgements from one person.

![shapes](poc6_shapes.png)

## The pipeline is not a heart trick

The same code, unchanged, on four shapes chosen to stress it differently — and
all four come out recognisable.

| shape | distance | vs nearest confusable shape | ratio | backtracked | route |
| --- | ---: | --- | ---: | ---: | ---: |
| crescent | 0.047 | heart (0.540) | **0.09** | 14 | 11.92 km |
| star5 | 0.079 | heart (0.325) | 0.24 | 16 | 9.50 km |
| heart | 0.061 | triangle (0.212) | 0.29 | 5 | 8.09 km |
| triangle | 0.054 | heart (0.212) | 0.25 | 5 | 7.75 km |

Raw distances are **not** comparable across shapes — a crescent's normalised
form has far more contour per unit radius than a triangle's. The `ratio` column
is: how far the route sits from its own target, divided by how far that target
sits from the shape most easily mistaken for it. Every shape lands well under 1,
so none is close to being confusable with another. The crescent wins outright at
0.09, because it is so distinctive that even a loose fit cannot be read as
anything else.

**Detour ratio is nearly identical across all four (1.24–1.29×)**, so the street
network costs about the same in path length whatever it is drawing. What
separates the shapes is backtracking: **star and crescent need three times as
many doubled-back segments as heart and triangle** (16 and 14 against 5 and 5).
That is the price of deep concavity — a notch running into the middle of a star
has to be entered and left the same way, because Taipei has no street that
threads it.

My prediction going in was that the star would be worst and the convex triangle
easiest. Half right: the star is indeed the hardest to fit, but the triangle is
not the easiest to *recognise* — it is the shape most easily confused with
something else (0.212 from a heart), so its comfortable fit buys less.

### Rotation is searched again

POC 3 locked orientation upright; POC 5's rater found tilt does not reduce
recognisability, and POC 5's corrected metric is rotation-invariant, so tilt can
be neither penalised nor gamed. Orientation is now a free parameter and the
search uses it: the winners sit at 300° (heart), 150° (star), 150° (crescent)
and 120° (triangle). A star whose points fall along the avenues only exists if
you look for it.

### The metric got faster, not slower

Rotation alignment is free. Minimising the squared distance over the angle turns
the cross-correlation's real part into its magnitude:

```
min_θ Σ|a_i − e^{iθ}·b_{i+k}|²  =  Σ|a|² + Σ|b|² − 2·|Σ a_i·conj(b_{i+k})|
```

so one FFT still serves every cyclic shift *and* every rotation — 0.81 ms per
call. `shape_metrics.shape_distance()` is the endorsed metric; rotation
invariance is exact (a heart rotated 30°, 90° or 180° scores 0.00000 against
itself), the diagonal of the cross-shape matrix is zero, and the off-diagonal
ordering is sensible.

## The second-rater task

**https://claude.ai/code/artifact/a9416012-ed04-4540-a7c0-df4d40a72317**

14 trials, about 3 minutes. It asks two questions and nothing else:

- **Tilt (10 trials)** — the same route shown twice, one copy rotated 20° or
  40°, across all four shapes. This is the direct replication of the finding
  that reversed POC 3 and POC 4.
- **Feature (2 trials)** — a shape with its defining feature flattened (the
  heart's cleft, one of the star's notches) against the *same* route with
  **identical per-point displacements** applied a quarter-turn away. Only the
  location of the deformation differs.

Plus 2 anchors with known answers and 2 repeats for self-consistency.

Design notes carried over from POC 5's mistakes: no ideal contour is drawn (with
a target on screen the judgement becomes "does it hug the line"), no street
background, "about the same" is a deliberate click with no keyboard shortcut,
reaction time is recorded per trial, and baseline routes are shown **upright** —
un-rotated by their placement angle, since a tilt question whose untilted member
already sits at 300° tests nothing.

The page asks for a name and namespaces every answer by it, so several people
can share one link without overwriting each other.

**Constraint worth knowing before you recruit:** an artifact declaring the `db`
capability is organisation-internal and cannot be shared publicly. A rater
outside your Claude organisation will not be able to open it — in that case the
page still works and shows a copyable JSON blob at the end, which they can send
back by any route.

## Limits

- Four shapes, one city. Nothing here says this survives a shape with a hole in
  it, disconnected parts, or fine detail at street scale.
- The width is fixed at 2 km for every shape, which flatters the crescent (long
  perimeter, so more contour per metre of error) and penalises nothing in
  particular. Searching scale still needs a scale-invariant objective.
- The star's 16 backtracked segments are a real artifact, not a rounding error;
  at a glance the route reads as a star, but a walker would notice re-walking
  the same alleys.
- POC 5's search re-run used the superseded rotation-sensitive metric. POC 6's
  search uses the corrected one, so the two are not directly comparable.

## Recommendation for POC 7

Depends on what comes back from the second rater.

**If tilt replicates** (rotated pairs called "about the same" again), the metric
question is closed and the next bottleneck is shape *acquisition* — text-to-shape
or image-to-shape — feeding this pipeline, which is now shape-agnostic and takes
any ordered closed contour. The natural interface is exactly that: a contour in,
a route out.

**If it does not replicate**, POC 5's conclusion was one person's idiosyncrasy,
the rotation search here has to be re-locked, and the metric needs its rotation
term back — in which case the honest move is a third rater before touching the
code again, not another reversal on n=1.

Either way, the concavity cost measured here is the first result in this project
that no metric argument can talk away: deep notches need backtracking, and no
choice of objective function changes what the street network physically offers.
