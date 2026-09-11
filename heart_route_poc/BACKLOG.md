# Backlog — deferred, with the reason

Things measured or reasoned about but not built. Kept here so they are decisions
rather than omissions.

## 1. Multi-contour shapes — blocks text-to-shape

**What.** Every stage of the pipeline takes ONE closed curve: `shape_library`,
`place_shape`, the Viterbi matcher, `shape_distance`. A shape with a hole or a
separate part cannot be expressed.

**Why it matters more than it looks.** POC 8 measured Chrome's dinosaur eye at
13×12 px — 6.4% of the shape's width, or 128 m at a 2 km target, comfortably
above the ~50 m this street network resolves. It is not too small to draw; it is
structurally unrepresentable.

The same limit blocks the biggest unbuilt feature in the original brief:
**text-to-shape**. The letters `A B D O P Q R` all have counters. "LOVE" cannot
be drawn because of the O.

**What it needs.** Not just plumbing. A product decision comes first: if a shape
is two closed loops, does the walker do two separate walks? One walk with a
marked gap between loops? A connecting leg that is drawn differently on the map?
The answer changes the data model before any code changes.

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

## 4. A rater round on feature destruction

POC 7 found that merging the dinosaur's legs costs 0.060 in metric terms, below
the ~0.10 threshold at which a person reliably sees a difference — while a
defining feature is gone. That is POC 4's cleft finding at larger scale, and it
has never been put to a rater on a complex shape. Needs a fresh rater, since the
existing one has done three rounds.

## 5. Detour ratio as a constant

`route_feasibility` assumes ~1.30. Stable across five shapes at 2 km, and
validated in POC 9 across sizes — but it is an empirical constant from one city,
and a different street grid would move it.
