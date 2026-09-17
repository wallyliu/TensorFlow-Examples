"""
Read the hand-drawn-against-traced answers.

The comparison is within-subject in the strongest sense available: the same
rater, the same option list, the same session, and for five subjects the same
right answer reached by two different drawings. So the paired rows are the
result and everything else is context.

McNemar on the five pairs, because they are matched - a pair where both arms
were named, or neither, carries no information about WHICH drawing is better,
and only the split pairs do.

Run:  python -m experiments.poc36_analyse <dir of response .json files>
"""

from __future__ import annotations

import collections
import json
import math
import sys
from pathlib import Path

from scipy.stats import binomtest


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
    items = {i["id"]: i for i in json.loads(
        (Path(__file__).resolve().parents[1] / "results"
         / "poc36_stimuli.json").read_text())} if False else None

    # the task page carries arm and drawing on every answer's item
    task = (Path(__file__).resolve().parents[1] / "results" / "poc36_task.html")
    import re
    data = json.loads(re.search(r"var DATA = (\{.*?\});\n", task.read_text(),
                                re.S).group(1))
    meta = {i["id"]: i for i in data["items"]}
    for r in rows:
        info = meta.get(r["item"], {})
        r["arm"] = info.get("arm", "?")
        r["drawing"] = info.get("drawing", r["shape"])

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
    for arm in ("hand", "traced", "anchor"):
        group = by_arm.get(arm, [])
        if not group:
            continue
        h = sum(r["correct"] for r in group)
        lo, hi = wilson(h, len(group))
        print(f"  {arm:7s} {h:2d}/{len(group):2d} = {h / len(group):4.0%} "
              f"[{lo:.0%}-{hi:.0%}]")

    # --- THE PAIRS ---------------------------------------------------------
    paired: dict = collections.defaultdict(dict)
    for r in rows:
        if r["arm"] in ("hand", "traced"):
            name = r["drawing"][2:] if r["drawing"].startswith("e_") else r["drawing"]
            paired[(r["session"], name)][r["arm"]] = r
    both = {k: v for k, v in paired.items() if len(v) == 2}
    print(f"\n{len(both)} matched pairs")
    hand_only = traced_only = agree = 0
    for (session, name), arms in sorted(both.items(), key=lambda kv: kv[0][1]):
        h, t = arms["hand"], arms["traced"]
        mark = {(True, True): "both", (False, False): "neither",
                (True, False): "HAND", (False, True): "TRACED"}[
            (bool(h["correct"]), bool(t["correct"]))]
        if mark == "HAND":
            hand_only += 1
        elif mark == "TRACED":
            traced_only += 1
        else:
            agree += 1
        print(f"  {name:10s} hand d={h['distance']:.3f} "
              f"{'named' if h['correct'] else (h['chosen'] if h['chosen'] != '__none__' else '-')}"
              f"   traced d={t['distance']:.3f} "
              f"{'named' if t['correct'] else (t['chosen'] if t['chosen'] != '__none__' else '-')}"
              f"   -> {mark}")
    split = hand_only + traced_only
    print(f"\n  agree on {agree}, split on {split} "
          f"(hand only {hand_only}, traced only {traced_only})")
    if split:
        p = binomtest(traced_only, split, 0.5).pvalue
        print(f"  McNemar (exact binomial on the split pairs): p = {p:.3f}")
    else:
        print("  no split pairs: this many raters cannot separate the arms")

    print("\nevery item:")
    for r in sorted(rows, key=lambda r: (r["arm"], r["drawing"])):
        got = "named" if r["correct"] else (
            "cannot tell" if r["chosen"] == "__none__" else "-> " + r["chosen"])
        print(f"  {r['arm']:7s} {r['drawing']:16s} d={r['distance']:.3f} "
              f"exc={meta[r['item']]['excursion']:.3f} "
              f"{meta[r['item']]['route_km']:5.1f} km  {got}")

    if len(sessions) < 3:
        print(f"\nCAVEAT: {len(sessions)} rater. Five pairs is five matched "
              f"observations; a McNemar on that cannot reach significance "
              f"unless every pair splits the same way.")


if __name__ == "__main__":
    main()
