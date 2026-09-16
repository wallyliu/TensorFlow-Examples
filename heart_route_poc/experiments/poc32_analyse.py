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

import json
import math
import sys
from pathlib import Path

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

    if len(sessions) < 3:
        print(f"\nCAVEAT: {len(sessions)} rater. Nothing above separates "
              f"'this shape is unrecognisable' from 'this person did not see "
              f"it', and a per-shape denominator of {len(rows) // len(by_shape)} "
              f"cannot carry a threshold. Treat it as a list of what to look "
              f"at next, not as a measurement.")


if __name__ == "__main__":
    main()
