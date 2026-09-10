"""
POC 5, step 2 - choose which pairs to put to a human.

With 15 shapes there are 105 possible pairs and no reason to judge them all.
The informative ones are where the candidate metrics DISAGREE: a pair both
metrics rank the same way cannot tell them apart, however obvious it looks.

The selection is therefore built around disagreements, plus:

  * anchors  - pairs so lopsided that getting one "wrong" means the rater was
               not really looking. These validate the rater, not the metrics.
  * repeats  - a handful of pairs shown twice, well separated. The rate at
               which the rater contradicts THEMSELVES is the ceiling on any
               agreement score, and without it an agreement of 0.8 cannot be
               told from a perfect metric measured against a noisy rater.
  * probes   - the cleft-vs-flank pair POC 4 could not settle, and the tilted
               route the incumbent metric could not distinguish.

Run:  python poc5_build_pairs.py
Out:  poc5_pairs.json
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np

POOL = Path(__file__).with_name("poc5_pool.npz")
OUT_JSON = Path(__file__).with_name("poc5_pairs.json")

METRIC_NAMES = ["chamfer_placed", "chamfer_upright", "procrustes_upright", "turning_upright"]
N_DISAGREE = 14
N_AGREE = 5
N_REPEATS = 5
SEED = 20260910


def to_svg_path(xy: np.ndarray, size: float = 100.0, margin: float = 8.0) -> str:
    """
    Normalise a route and emit an SVG path.

    Position and size are normalised away so neither can act as a cue.
    Orientation is deliberately NOT normalised - tilt is one of the things
    under test - and the y axis is flipped because SVG counts downward while
    the projected coordinates count north.
    """
    pts = np.vstack([xy, xy[:1]])
    pts = pts - pts.mean(axis=0)
    pts = pts / np.abs(pts).max()  # fit the wider axis into [-1, 1]

    span = (size - 2 * margin) / 2.0
    x = size / 2.0 + pts[:, 0] * span
    y = size / 2.0 - pts[:, 1] * span
    body = " ".join(f"{a:.2f},{b:.2f}" for a, b in zip(x, y))
    return "M" + body.replace(" ", " L", 1).replace(",", " ", 1) + " Z" if False else (
        "M " + " L ".join(f"{a:.2f} {b:.2f}" for a, b in zip(x, y)) + " Z"
    )


def main() -> None:
    data = np.load(POOL, allow_pickle=True)
    ids = [str(i) for i in data["ids"]]
    scores = {i: dict(zip(METRIC_NAMES, data[f"{i}__scores"])) for i in ids}
    shapes = {i: to_svg_path(data[f"{i}__xy"]) for i in ids}

    rng = np.random.default_rng(SEED)

    def ordering(pair, metric):
        a, b = pair
        return np.sign(scores[a][metric] - scores[b][metric])

    disagree, agree = [], []
    for pair in combinations(ids, 2):
        cu = ordering(pair, "chamfer_upright")
        pu = ordering(pair, "procrustes_upright")
        cp = ordering(pair, "chamfer_placed")
        gap = abs(scores[pair[0]]["procrustes_upright"] - scores[pair[1]]["procrustes_upright"])
        (disagree if (cu != pu or cp != pu) else agree).append((pair, gap))

    # Among disagreements prefer the widest procrustes gap: those are the pairs
    # where the metrics differ most sharply, so a human answer is most decisive.
    disagree.sort(key=lambda item: -item[1])
    agree.sort(key=lambda item: -item[1])

    chosen = [p for p, _ in disagree[:N_DISAGREE]] + [p for p, _ in agree[:N_AGREE]]

    # The two probes POC 3 and POC 4 left open, forced into the set.
    for probe in (("cleft_filled", "flank_changed"), ("tilted30", "real10")):
        if probe not in chosen and tuple(reversed(probe)) not in chosen:
            chosen.append(probe)

    repeats = [chosen[i] for i in rng.choice(len(chosen), N_REPEATS, replace=False)]

    trials = []
    for index, pair in enumerate(chosen):
        trials.append({"pair_id": f"p{index:02d}", "items": list(pair), "repeat_of": None})
    for index, pair in enumerate(repeats):
        trials.append({"pair_id": f"r{index:02d}", "items": list(pair),
                       "repeat_of": next(t["pair_id"] for t in trials
                                         if tuple(t["items"]) == pair and t["repeat_of"] is None)})

    # Shuffle order, and independently shuffle which side each shape appears on.
    order = rng.permutation(len(trials))
    trials = [trials[i] for i in order]
    for trial in trials:
        if rng.random() < 0.5:
            trial["items"] = trial["items"][::-1]

    payload = {
        "shapes": shapes,
        "trials": trials,
        "scores": {i: {k: float(v) for k, v in s.items()} for i, s in scores.items()},
    }
    OUT_JSON.write_text(json.dumps(payload, separators=(",", ":")))

    print(f"{len(disagree)} disagreeing pairs available, {len(agree)} agreeing")
    print(f"selected {len(chosen)} unique + {N_REPEATS} repeats = {len(trials)} trials")
    print(f"payload {OUT_JSON.stat().st_size / 1024:.0f} KB")
    print("\nprobe pairs included:")
    for trial in trials:
        if set(trial["items"]) in ({"cleft_filled", "flank_changed"}, {"tilted30", "real10"}):
            a, b = trial["items"]
            print(f"  {trial['pair_id']}: {a} vs {b}")
            for metric in METRIC_NAMES:
                worse = a if scores[a][metric] > scores[b][metric] else b
                print(f"      {metric:<20} says {worse} is worse")


if __name__ == "__main__":
    main()
