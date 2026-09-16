"""
Read the blind identification answers and say what they mean.

Three questions, in the order they matter:

  WHICH DRAWINGS DO NOT READ. A shape missed at its own closest fit is a
  drawing problem, not a routing problem - nothing downstream will rescue it.

  WHERE RECOGNITION FALLS OFF. Correctness against shape distance, pooled and
  per shape, against the 0.201 that recognition.py currently applies to all
  twelve pack shapes.

  CAT vs CAT_HEAD, which ship side by side precisely because nobody knew.

Wilson intervals throughout, because with one or two raters a proportion of
1.0 over two items is not evidence of anything and an interval says so where a
percentage does not. With a single rater nothing here separates "this shape is
unrecognisable" from "this person did not see it", and the report says so
rather than implying otherwise.

Run:  python -m experiments.poc32_analyse <dir of response .json files>
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

CHANCE = 1.0 / 16.0          # fifteen shapes plus "cannot tell"
POOLED_THRESHOLD = 0.201     # what recognition.py currently assumes


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = hits / n
    d = 1 + z * z / n
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



def agreement(rows: list) -> None:
    """Do the raters see the same thing? Without this a split is unreadable."""
    by_item: dict = collections.defaultdict(dict)
    for r in rows:
        by_item[r["item"]][r["session"]] = r
    pairs = [d for d in by_item.values() if len(d) >= 2]
    if not pairs:
        return
    both_right = sum(all(x["correct"] for x in d.values()) for d in pairs)
    both_wrong = sum(not any(x["correct"] for x in d.values()) for d in pairs)
    n = len(pairs)
    observed = (both_right + both_wrong) / n
    rates = []
    for session in sorted({r["session"] for r in rows}):
        mine = [r["correct"] for r in rows if r["session"] == session]
        rates.append(sum(mine) / len(mine))
    expected = rates[0] * rates[1] + (1 - rates[0]) * (1 - rates[1])
    kappa = (observed - expected) / (1 - expected) if expected < 1 else float("nan")
    print(f"\ninter-rater: agree on {both_right + both_wrong}/{n} items "
          f"({both_right} both right, {both_wrong} both wrong), "
          f"disagree on {n - both_right - both_wrong}")
    print(f"             observed {observed:.0%}, chance {expected:.0%}, "
          f"kappa {kappa:.2f}")


def between_shapes(rows: list, shuffles: int = 20000) -> None:
    """Is recognition a property of the SHAPE or of the shape distance?

    recognition.py answers "the distance": every shape gets a logistic curve
    over it. If that is right, per-shape accuracy should look like what you get
    by dealing the same answers out at random. This deals them out and checks.
    """
    by_shape: dict = collections.defaultdict(list)
    for r in rows:
        by_shape[r["shape"]].append(bool(r["correct"]))
    sizes = [len(v) for v in by_shape.values()]
    observed = float(np.var([np.mean(v) for v in by_shape.values()]))

    flat = [bool(r["correct"]) for r in rows]
    random.seed(0)
    hits = 0
    for _ in range(shuffles):
        deck = flat[:]
        random.shuffle(deck)
        groups, at = [], 0
        for size in sizes:
            groups.append(np.mean(deck[at:at + size]))
            at += size
        if np.var(groups) >= observed:
            hits += 1
    p = (hits + 1) / (shuffles + 1)
    print(f"\nper-shape accuracy variance {observed:.3f}, "
          f"permutation p = {p:.4f} ({shuffles:,} shuffles)")
    acc = {k: float(np.mean(v)) for k, v in by_shape.items()}
    print("  always:", ", ".join(sorted(k for k, v in acc.items() if v == 1.0)) or "-")
    print("  never: ", ", ".join(sorted(k for k, v in acc.items() if v == 0.0)) or "-")
    print("  mixed: ", ", ".join(f"{k} {v:.2f}"
                                 for k, v in sorted(acc.items()) if 0 < v < 1) or "-")


def against_poc29(rows: list, folder: Path) -> None:
    """The same distance band, the old shapes and the new ones.

    Below 0.10 a route is about as close to its target as this project gets, so
    if the drawing is any good this is where it reads.
    """
    old = folder.parent
    for candidate in (Path("results/poc29_recognisability.json"),
                      old / "poc29_recognisability.json"):
        if candidate.exists():
            band = json.loads(candidate.read_text())["bands"][0]
            break
    else:
        return
    new = [r for r in rows if r["distance"] < 0.10]
    hits = sum(r["correct"] for r in new)
    odds, p = fisher_exact([[band["correct"], band["n"] - band["correct"]],
                            [hits, len(new) - hits]])
    print(f"\nbelow d={band['hi']:.2f}, the closest this project fits:")
    print(f"  the original five  {band['correct']:2d}/{band['n']:2d} = "
          f"{band['correct'] / band['n']:.0%}   (POC 29)")
    print(f"  this pack          {hits:2d}/{len(new):2d} = "
          f"{hits / len(new):.0%}")
    print(f"  Fisher exact p = {p:.5f}, odds ratio {odds:.1f}")
    print("  CONFOUNDED: POC 29 offered five options and this task sixteen, "
          "and the raters differ. Anchor items - the original shapes inside "
          "THIS task - would settle it; this comparison only motivates them.")


def main() -> None:
    folder = Path(sys.argv[1])
    rows = load(folder)
    sessions = sorted({r["session"] for r in rows})
    print(f"{len(rows)} answers from {len(sessions)} rater"
          f"{'s' if len(sessions) != 1 else ''}\n")

    hits = sum(r["correct"] for r in rows)
    blank = sum(r["chosen"] == "__none__" for r in rows)
    wrong = len(rows) - hits - blank
    lo, hi = wilson(hits, len(rows))
    print(f"overall  {hits}/{len(rows)} correct ({hits / len(rows):.0%}, "
          f"95% CI {lo:.0%}-{hi:.0%}); chance is {CHANCE:.0%}")
    print(f"         {blank} cannot-tell, {wrong} misidentified\n")

    # --- per shape, closest fit vs worst -----------------------------------
    by_shape: dict = {}
    for r in rows:
        by_shape.setdefault(r["shape"], []).append(r)
    print(f"{'shape':10s} {'best':>26s}   {'hard':>26s}")
    failures = []
    for shape in sorted(by_shape):
        group = sorted(by_shape[shape], key=lambda r: r["distance"])
        half = len(group) // 2 or 1
        easy, hard = group[:half], group[half:]
        def cell(items):
            if not items:
                return " " * 26
            h = sum(i["correct"] for i in items)
            d = sum(i["distance"] for i in items) / len(items)
            mark = "ok " if h == len(items) else ("-- " if h == 0 else "~  ")
            return f"{mark}{h}/{len(items)} @ d={d:.3f}".rjust(26)
        if easy and not any(i["correct"] for i in easy):
            failures.append(shape)
        print(f"{shape:10s} {cell(easy)}   {cell(hard)}")

    print()
    if failures:
        print("MISSED AT ITS OWN CLOSEST FIT - the drawing, not the route:")
        for shape in failures:
            said = [r["chosen"] for r in by_shape[shape]]
            print(f"  {shape:10s} called {said}")
    else:
        print("every shape was identified at its closest fit")

    # --- what the misses were called ---------------------------------------
    confusions = [(r["shape"], r["chosen"]) for r in rows
                  if not r["correct"] and r["chosen"] != "__none__"]
    if confusions:
        print("\nmisidentified as:")
        for true, said in confusions:
            print(f"  {true} -> {said}")

    # --- recognition against distance --------------------------------------
    print("\nby shape distance:")
    bands = [(0.0, 0.07), (0.07, 0.10), (0.10, 0.14), (0.14, 0.20), (0.20, 1.0)]
    for lo_d, hi_d in bands:
        band = [r for r in rows if lo_d <= r["distance"] < hi_d]
        if not band:
            continue
        h = sum(r["correct"] for r in band)
        lo, hi = wilson(h, len(band))
        bar = "#" * round(20 * h / len(band))
        print(f"  {lo_d:.2f}-{hi_d if hi_d < 1 else 1:.2f}  "
              f"{h:2d}/{len(band):2d}  {h / len(band):4.0%} "
              f"[{lo:.0%}-{hi:.0%}]  {bar}")

    above = [r for r in rows if r["distance"] >= POOLED_THRESHOLD]
    if above:
        h = sum(r["correct"] for r in above)
        print(f"\n  at or above the assumed threshold {POOLED_THRESHOLD}: "
              f"{h}/{len(above)} correct")

    # --- cat vs cat_head ----------------------------------------------------
    print()
    for shape in ("cat", "cat_head"):
        group = by_shape.get(shape, [])
        if not group:
            continue
        h = sum(r["correct"] for r in group)
        lo, hi = wilson(h, len(group))
        detail = ", ".join(f"d={r['distance']:.3f}->"
                           f"{'right' if r['correct'] else r['chosen']}"
                           for r in sorted(group, key=lambda r: r["distance"]))
        print(f"{shape:9s} {h}/{len(group)} [{lo:.0%}-{hi:.0%}]  {detail}")

    agreement(rows)
    between_shapes(rows)
    against_poc29(rows, folder)

    if len(sessions) < 3:
        print(f"\nCAVEAT: {len(sessions)} rater. Nothing above separates "
              f"'this shape is unrecognisable' from 'this person did not see "
              f"it', and a per-shape denominator of {len(rows) // len(by_shape)} "
              f"cannot carry a threshold. Treat it as a list of what to look "
              f"at next, not as a measurement.")


if __name__ == "__main__":
    main()
