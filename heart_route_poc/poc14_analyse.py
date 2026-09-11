"""
Pool both rounds of the rater task.

The dinosaur ladder was kept byte-identical across rounds so the sessions could
be pooled, which was the whole point: round one produced four decided judgements
all in the same direction, and four judgements cannot reach significance however
lopsided they are.

The text block differs between rounds and is reported separately.

Run:  python poc14_analyse.py
Out:  poc14_analysis.png, poc14_analysis.json
"""

from __future__ import annotations

import json
from collections import Counter
from math import comb
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
DINO = json.loads((HERE / "poc13_dino.json").read_text())
OUT_PNG = HERE / "poc14_analysis.png"
OUT_JSON = HERE / "poc14_analysis.json"

LADDER = ["L1", "L2", "L3", "L4"]
MERGED, NOISE, TIE, INK = "#2f5d50", "#b4622c", "#8a8f8a", "#191b1a"


def sign_test(successes: int, trials: int) -> float:
    """Two-sided probability of a split this lopsided under no preference."""
    if trials == 0:
        return 1.0
    k = max(successes, trials - successes)
    return min(1.0, 2 * sum(comb(trials, i) for i in range(k, trials + 1)) / 2 ** trials)


def side(choice: str) -> str:
    if choice.endswith("_merged"):
        return "merged"
    if choice.endswith("_noise"):
        return "noise"
    return choice


def main() -> None:
    paths = sorted(HERE.glob("rater/poc1*_session_*.json"))
    sessions = [json.loads(p.read_text()) for p in paths]
    byid = [{a["id"]: a for a in s["answers"]} for s in sessions]
    versions = [s.get("version", "v1") for s in sessions]
    print(f"{len(sessions)} sessions: " + ", ".join(
        f"{p.stem.split('_')[-1]} ({v})" for p, v in zip(paths, versions)) + "\n")

    report = {"sessions": [{"id": s.get("session"), "version": v,
                            "total_ms": s.get("total_ms")}
                           for s, v in zip(sessions, versions)]}

    # ---- the ladder, pooled -------------------------------------------------
    print("iso-distance ladder - both members of each pair are the same")
    print("shape distance from the clean dinosaur\n")
    header = f"  {'rung':<6}{'distance':>9}" + "".join(f"{'r' + str(i + 1):>10}"
                                                       for i in range(len(byid)))
    print(header)
    rung_choices = {}
    for rung in LADDER:
        d = DINO[f"{rung}_merged"]["distance_from_clean"]
        choices = [side(s[rung]["chose"]) for s in byid]
        rung_choices[rung] = choices
        print(f"  {rung:<6}{d:9.3f}" + "".join(f"{c:>10}" for c in choices))

    # Repeats are the same question asked twice and are not independent of the
    # original, so the headline test excludes them and they are reported as
    # consistency instead.
    first_pass = [side(s[r]["chose"]) for r in LADDER for s in byid]
    decided = [c for c in first_pass if c in ("merged", "noise")]
    wins = sum(c == "merged" for c in decided)
    p = sign_test(wins, len(decided))
    print(f"\n  first-pass judgements: {len(first_pass)}, "
          f"decided {len(decided)}, feature-destroyed preferred {wins}")
    print(f"  sign test p = {p:.4f}")

    with_rep = decided + [side(s[f"{r}_repeat"]["chose"])
                          for r in ("L2", "L4") for s in byid]
    with_rep = [c for c in with_rep if c in ("merged", "noise")]
    wins_rep = sum(c == "merged" for c in with_rep)
    print(f"  including repeats (not independent): {wins_rep}/{len(with_rep)}, "
          f"p = {sign_test(wins_rep, len(with_rep)):.5f}")

    report["ladder"] = {
        "per_rung": {r: rung_choices[r] for r in LADDER},
        "decided": len(decided), "merged_wins": wins, "sign_test_p": p,
        "with_repeats": {"decided": len(with_rep), "merged_wins": wins_rep,
                         "sign_test_p": sign_test(wins_rep, len(with_rep))}}

    # ---- consistency and catches -------------------------------------------
    same = sum(s[r]["chose"] == s[f"{r}_repeat"]["chose"]
               for r in ("L2", "L4") for s in byid)
    total = 2 * len(byid)
    print(f"\nself-consistency on repeats: {same}/{total}")
    catch = Counter(s["catch_clean"]["chose"] for s in byid)
    print(f"catch (clean vs scrambled): {dict(catch)}")
    bothbad = Counter(s["catch_bothbad"]["chose"] for s in byid)
    print(f"catch (scrambled vs L4 noise): {dict(bothbad)}")
    report["repeat_agreement"] = f"{same}/{total}"
    report["catch_clean"] = dict(catch)
    report["catch_bothbad"] = dict(bothbad)

    # ---- text, reported per round ------------------------------------------
    print("\ntext, read BEFORE the word appeared on the page")
    reads = []
    for s, v in zip(byid, versions):
        for key in ("read_outline", "read_mst", "read_rail", "read_stroke"):
            if key in s:
                a = s[key]
                reads.append({"version": v, "trial": key, "image": a["image"],
                              "answer": a["chose"], "ms": a["ms"]})
                print(f"  [{v}] {a['image']:<22} -> {a['chose']:<8} ({a['ms']} ms)")
    report["reads"] = reads

    print("\ntext, after being told the word is LIT")
    rated = []
    for s, v in zip(byid, versions):
        for key, a in s.items():
            if key.startswith("rate_") or key.startswith("pair_"):
                rated.append({"version": v, "trial": key, "answer": a["chose"],
                              "ms": a["ms"]})
                print(f"  [{v}] {key:<22} -> {a['chose']}  ({a['ms']} ms)")
    report["rated"] = rated

    # ---- figure -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.3))
    n = len(byid)
    xs = [DINO[f"{r}_merged"]["distance_from_clean"] for r in LADDER]
    for i, rung in enumerate(LADDER):
        for j, c in enumerate(rung_choices[rung]):
            color = MERGED if c == "merged" else NOISE if c == "noise" else TIE
            ax1.bar(i + (j - (n - 1) / 2) * 0.26, 1, width=0.24, color=color)
    ax1.set_xticks(range(len(LADDER)))
    ax1.set_xticklabels([f"{r}\n{x:.3f}" for r, x in zip(LADDER, xs)])
    ax1.set_yticks([])
    ax1.set_ylim(0, 1.3)
    ax1.set_title("Which is more dinosaur-like?  one bar per rater\n"
                  "green = the one with a feature destroyed, grey = tie",
                  fontsize=10)
    ax1.set_xlabel("rung, and the shape distance both members share", fontsize=9)
    for sp in ax1.spines.values():
        sp.set_visible(False)

    for j, s in enumerate(byid):
        times = [s[r]["ms"] for r in LADDER]
        ax2.plot(xs, times, "o-", lw=1.5, ms=6, alpha=0.85,
                 label=f"rater {j + 1}")
    ax2.set_xlabel("shape distance (identical for both members)", fontsize=9)
    ax2.set_ylabel("decision time (ms)", fontsize=9)
    ax2.set_title("The metric calls all four pairs equally matched.\n"
                  "All three take longest on L1 - the rung they all call a tie.",
                  fontsize=10)
    ax2.legend(frameon=False, fontsize=9)
    ax2.grid(alpha=0.25, lw=0.6)
    for sp in ("top", "right"):
        ax2.spines[sp].set_visible(False)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
