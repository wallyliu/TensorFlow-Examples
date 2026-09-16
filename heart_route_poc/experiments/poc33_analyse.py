"""
Read the anchored answers. The anchor comparison is the point.

POC 32 compared this pack against POC 29's original five and found 27/28
against 16/32 below a shape distance of 0.10, but across two tasks with
different option counts and different people. Here the two sets sit in ONE
task, so the comparison is within-subject and both confounds are gone: if the
pack still loses, the metric distance genuinely means something different for
these shapes, which is BACKLOG 23 in human form.

Everything else - Wilson intervals, the per-shape split, the refusal to read a
threshold off two items - follows POC 32.

Run:  python -m experiments.poc33_analyse <dir of response .json files>
"""

from __future__ import annotations

import collections
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
from scipy.stats import fisher_exact

BELOW = 0.10          # the closest this project fits


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p, d = hits / n, 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def load(folder: Path) -> list:
    rows = []
    for f in sorted(folder.rglob("*.json")):
        doc = json.loads(f.read_text())
        for a in doc.get("answers", []):
            rows.append(dict(a, session=doc.get("session", f.stem)))
    return rows


def main() -> None:
    rows = load(Path(sys.argv[1]))
    items = json.loads((Path(__file__).resolve().parents[1]
                        / "results" / "poc33_stimuli.json").read_text())
    anchors = {r["shape"] for r in items if r.get("anchor")}
    for r in rows:
        r["anchor"] = r["shape"] in anchors

    sessions = sorted({r["session"] for r in rows})
    hits = sum(r["correct"] for r in rows)
    blank = sum(r["chosen"] == "__none__" for r in rows)
    lo, hi = wilson(hits, len(rows))
    print(f"{len(rows)} answers from {len(sessions)} rater"
          f"{'s' if len(sessions) != 1 else ''}; chance {1 / 21:.0%}")
    print(f"overall {hits}/{len(rows)} = {hits / len(rows):.0%} "
          f"[{lo:.0%}-{hi:.0%}]; {blank} cannot-tell, "
          f"{len(rows) - hits - blank} misidentified\n")

    # --- THE ANCHOR COMPARISON -------------------------------------------
    print(f"WITHIN ONE TASK, one option list, the same people:")
    for label, want in (("the original five", True), ("this pack", False)):
        group = [r for r in rows if r["anchor"] is want]
        h = sum(r["correct"] for r in group)
        near = [r for r in group if r["distance"] < BELOW]
        hn = sum(r["correct"] for r in near)
        lo, hi = wilson(h, len(group))
        print(f"  {label:18s} {h:2d}/{len(group):2d} = {h / len(group):4.0%} "
              f"[{lo:.0%}-{hi:.0%}]     below d={BELOW}: "
              f"{hn}/{len(near)}" + (f" = {hn / len(near):.0%}" if near else ""))
    old = [r for r in rows if r["anchor"] and r["distance"] < BELOW]
    new = [r for r in rows if not r["anchor"] and r["distance"] < BELOW]
    if old and new:
        a, b = sum(r["correct"] for r in old), sum(r["correct"] for r in new)
        odds, p = fisher_exact([[a, len(old) - a], [b, len(new) - b]])
        print(f"  Fisher exact p = {p:.4f}, odds ratio {odds:.1f}  "
              f"(POC 32 across tasks: p = 0.00005, OR 27)")

    # --- per shape --------------------------------------------------------
    by_shape: dict = collections.defaultdict(list)
    for r in rows:
        by_shape[r["shape"]].append(r)
    print(f"\n{'shape':15s} {'':8s}  hits  distances")
    for shape in sorted(by_shape, key=lambda s: (-np.mean(
            [x["correct"] for x in by_shape[s]]), s)):
        g = sorted(by_shape[shape], key=lambda r: r["distance"])
        h = sum(r["correct"] for r in g)
        tag = "(anchor)" if shape in anchors else ""
        detail = "  ".join(f"{r['distance']:.3f}"
                           + ("+" if r["correct"] else
                              ("?" if r["chosen"] == "__none__" else
                               "->" + r["chosen"])) for r in g)
        print(f"{shape:15s} {tag:8s}  {h}/{len(g)}   {detail}")

    # --- is the variance between shapes? ----------------------------------
    groups = [[bool(x["correct"]) for x in v] for v in by_shape.values()]
    observed = float(np.var([np.mean(g) for g in groups]))
    flat = [bool(r["correct"]) for r in rows]
    random.seed(0)
    worse = 0
    for _ in range(20000):
        deck = flat[:]
        random.shuffle(deck)
        at, means = 0, []
        for g in groups:
            means.append(np.mean(deck[at:at + len(g)]))
            at += len(g)
        worse += np.var(means) >= observed
    print(f"\nper-shape variance {observed:.3f}, permutation p = "
          f"{(worse + 1) / 20001:.4f}")

    if len(sessions) < 3:
        print(f"\nCAVEAT: {len(sessions)} rater, two items per shape. The "
              f"anchor comparison is within-subject and survives that; the "
              f"per-shape rows do not.")


if __name__ == "__main__":
    main()
