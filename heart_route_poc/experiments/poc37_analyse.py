"""
Read round four's answers.

Two questions, and they are not equally well served by this design.

  HAND AGAINST EMOJI is matched: every rater sees both drawings of every
  subject, so the pairs are within-rater and McNemar on the split pairs is the
  test. That is the same instrument POC 36 used.

  NOTO AGAINST OPENMOJI is not matched. A rater sees one tracer per subject, by
  design - showing both would let them recognise the second from the first - so
  the two tracers are compared BETWEEN items and the answer accumulates slowly.
  Reported as a rate with an interval, and as the per-subject tally that says
  which drawing to keep, which is the decision this round exists to make.

Run:  python -m experiments.poc37_analyse <dir of response .json files>
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
TASK = RESULTS / "poc37_task.html"
EMOJI_ARMS = ("noto", "openmoji")


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
    for arm in ("hand", "noto", "openmoji", "anchor"):
        group = by_arm.get(arm, [])
        if not group:
            continue
        h = sum(r["correct"] for r in group)
        lo, hi = wilson(h, len(group))
        print(f"  {arm:9s} {h:2d}/{len(group):2d} = {h / len(group):4.0%} "
              f"[{lo:.0%}-{hi:.0%}]")

    # --- hand against whichever emoji arm this rater saw --------------------
    paired: dict = collections.defaultdict(dict)
    for r in rows:
        if r["arm"] == "hand":
            paired[(r["session"], r["subject"])]["hand"] = r
        elif r["arm"] in EMOJI_ARMS:
            paired[(r["session"], r["subject"])]["emoji"] = r
    both = {k: v for k, v in paired.items() if len(v) == 2}
    print(f"\n{len(both)} matched pairs (hand vs emoji)")
    hand_only = emoji_only = agree = 0
    for (session, name), arms in sorted(both.items(), key=lambda kv: kv[0][1]):
        h, e = arms["hand"], arms["emoji"]
        mark = {(True, True): "both", (False, False): "neither",
                (True, False): "HAND", (False, True): "EMOJI"}[
            (bool(h["correct"]), bool(e["correct"]))]
        if mark == "HAND":
            hand_only += 1
        elif mark == "EMOJI":
            emoji_only += 1
        else:
            agree += 1
        print(f"  {name:14s} hand d={h['distance']:.3f} "
              f"{'named' if h['correct'] else (h['chosen'] if h['chosen'] != '__none__' else '-')}"
              f"   {e['arm']:8s} d={e['distance']:.3f} "
              f"{'named' if e['correct'] else (e['chosen'] if e['chosen'] != '__none__' else '-')}"
              f"   -> {mark}")
    split = hand_only + emoji_only
    print(f"\n  agree on {agree}, split on {split} "
          f"(hand only {hand_only}, emoji only {emoji_only})")
    if split:
        p = binomtest(emoji_only, split, 0.5).pvalue
        print(f"  McNemar (exact binomial on the split pairs): p = {p:.3f}")
    else:
        print("  no split pairs: this many raters cannot separate the arms")

    # And the same test PER TRACER, which is the one that means something.
    # Pooling them asks "is hand better than emoji" when the two tracers are
    # nowhere near each other, and the pooled answer is then just whichever
    # tracer happened to be drawn more often.
    for tracer in EMOJI_ARMS:
        h = e = same = 0
        for arms in both.values():
            if arms["emoji"]["arm"] != tracer:
                continue
            a, b = bool(arms["hand"]["correct"]), bool(arms["emoji"]["correct"])
            if a and not b:
                h += 1
            elif b and not a:
                e += 1
            else:
                same += 1
        n = h + e
        line = (f"  hand vs {tracer:9s} {same + n:2d} pairs, {n} split "
                f"(hand {h}, {tracer} {e})")
        print(line + (f", p = {binomtest(e, n, 0.5).pvalue:.3f}" if n
                      else ", nothing to test"))

    # --- the two tracers, between items ------------------------------------
    print("\nNoto against OpenMoji (unmatched - one tracer per rater per "
          "subject)")
    for arm in EMOJI_ARMS:
        group = by_arm.get(arm, [])
        if not group:
            continue
        h = sum(r["correct"] for r in group)
        lo, hi = wilson(h, len(group))
        print(f"  {arm:9s} {h:2d}/{len(group):2d} = {h / len(group):4.0%} "
              f"[{lo:.0%}-{hi:.0%}]")

    # --- which drawing to keep, per subject --------------------------------
    print("\nper subject, named / shown:")
    tally: dict = collections.defaultdict(lambda: collections.defaultdict(
        lambda: [0, 0]))
    for r in rows:
        if r["arm"] == "anchor":
            continue
        cell = tally[r["subject"]][r["arm"]]
        cell[0] += int(bool(r["correct"]))
        cell[1] += 1
    for subject in sorted(tally):
        parts = []
        for arm in ("hand",) + EMOJI_ARMS:
            named, shown = tally[subject].get(arm, [0, 0])
            parts.append(f"{arm} {named}/{shown}" if shown else f"{arm} -")
        # A subject nobody named has no winner, and saying it does is how a
        # dead shape stays in the pack.
        scored = [(kv[1][0] / kv[1][1], kv[1][1], kv[0])
                  for kv in tally[subject].items() if kv[1][1]]
        top = max(scored)
        best = "none named" if top[0] == 0 else top[2]
        print(f"  {subject:14s} " + "  ".join(f"{p:14s}" for p in parts)
              + f"  -> {best}")

    print("\nevery item:")
    for r in sorted(rows, key=lambda r: (r["subject"], r["arm"])):
        got = "named" if r["correct"] else (
            "cannot tell" if r["chosen"] == "__none__" else "-> " + r["chosen"])
        print(f"  {r['arm']:9s} {r['drawing']:18s} d={r['distance']:.3f} "
              f"exc={meta[r['item']]['excursion']:.3f} "
              f"{meta[r['item']]['route_km']:5.1f} km  {got}")

    if len(sessions) < 3:
        print(f"\nNOTE: {len(sessions)} rater(s). Every rater adds twelve "
              f"hand-vs-emoji pairs and six items per tracer, and the McNemar "
              f"only sees the pairs that SPLIT. The tracer comparison needs "
              f"more raters than the arm comparison does.")


if __name__ == "__main__":
    main()
