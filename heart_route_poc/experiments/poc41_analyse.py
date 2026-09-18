"""
Read round five's answers.

One arm and one item per shape, so there are no pairs and no McNemar - the
question is simply what share of people name each traced subject, which is the
only quantity POC 39 found worth having. The three anchors are the check on the
round itself: they are 11/11 across four previous rounds, so if they slip here
the round is wrong rather than the shapes.

Run:  python -m experiments.poc41_analyse <dir of response .json files>
"""

from __future__ import annotations

import collections
import json
import math
import re
import sys
from pathlib import Path

from scipy.stats import binomtest

RESULTS = Path(__file__).resolve().parents[1] / "results"
TASK = RESULTS / "poc41_task.html"
ARMS = ("traced", "anchor")


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p, d = hits / n, 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def main() -> None:
    rows = []
    for f in sorted(Path(sys.argv[1]).rglob("*.json")):
        doc = json.loads(f.read_text())
        for a in doc.get("answers", []):
            rows.append(dict(a, session=doc.get("session", f.stem)))
    data = json.loads(re.search(r"var DATA = (\{.*?\});\n", TASK.read_text(),
                                re.S).group(1))
    meta = {i["id"]: i for i in data["items"]}
    for r in rows:
        info = meta.get(r["item"], {})
        r["arm"] = info.get("arm", "?")
        r["drawing"] = info.get("drawing", r["shape"])
        r["subject"] = info.get("subject", r["drawing"])

    sessions = sorted({r["session"] for r in rows})
    hits = sum(r["correct"] for r in rows)
    blank = sum(r["chosen"] == "__none__" for r in rows)
    lo, hi = wilson(hits, len(rows))
    print(f"{len(rows)} answers from {len(sessions)} rater"
          f"{'s' if len(sessions) != 1 else ''}; "
          f"chance {1 / len(data['options']):.0%}")
    print(f"overall {hits}/{len(rows)} = {hits / len(rows):.0%} "
          f"[{lo:.0%}-{hi:.0%}]; {blank} cannot-tell, "
          f"{len(rows) - hits - blank} misidentified\n")

    by_arm: dict = collections.defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    for arm in ARMS:
        group = by_arm.get(arm, [])
        if not group:
            continue
        h = sum(r["correct"] for r in group)
        lo, hi = wilson(h, len(group))
        print(f"  {arm:9s} {h:2d}/{len(group):2d} = {h / len(group):4.0%} "
              f"[{lo:.0%}-{hi:.0%}]")

    # --- the rate per shape, which is the whole point ---------------------
    print("\nper shape, named / shown:")
    tally: dict = collections.defaultdict(lambda: collections.defaultdict(
        lambda: [0, 0]))
    for r in rows:
        if r["arm"] == "anchor":
            continue
        cell = tally[r["subject"]][r["arm"]]
        cell[0] += int(bool(r["correct"]))
        cell[1] += 1
    for subject in sorted(tally):
        named = sum(v[0] for v in tally[subject].values())
        shown = sum(v[1] for v in tally[subject].values())
        lo, hi = wilson(named, shown)
        print(f"  {subject:14s} {named:2d}/{shown:2d} = {named / shown:4.0%} "
              f"[{lo:.0%}-{hi:.0%}]")

    print("\nevery item:")
    for r in sorted(rows, key=lambda r: (r["subject"], r["arm"])):
        got = "named" if r["correct"] else (
            "cannot tell" if r["chosen"] == "__none__" else "-> " + r["chosen"])
        print(f"  {r['arm']:9s} {r['drawing']:18s} d={r['distance']:.3f} "
              f"exc={meta[r['item']]['excursion']:.3f} "
              f"{meta[r['item']]['route_km']:5.1f} km  {got}")

    if len(sessions) < 3:
        print(f"\nNOTE: {len(sessions)} rater(s), so every shape rests on "
              f"{len(sessions)} answer(s). A 1/1 and a 0/1 are both consistent "
              f"with almost anything; this is a first look, not a rate.")


if __name__ == "__main__":
    main()
