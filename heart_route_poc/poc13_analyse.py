"""
What the rater said, and what it does and does not settle.

One rater, sixteen trials, 71 seconds of decision time. That is enough to
answer one question and not enough to answer the other, and the difference
between those two cases is the point of this file.

Run:  python poc13_analyse.py
Out:  poc13_analysis.png, poc13_analysis.json
"""

from __future__ import annotations

import json
from math import comb
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
SESSIONS = sorted((HERE / "rater").glob("poc13_session_*.json"))
DINO = json.loads((HERE / "poc13_dino.json").read_text())
CONDITIONS = json.loads((HERE / "poc13_conditions.json").read_text())
OUT_PNG = HERE / "poc13_analysis.png"
OUT_JSON = HERE / "poc13_analysis.json"

LADDER = ["L1", "L2", "L3", "L4"]
INK, MERGED, NOISE, TIE = "#191b1a", "#2f5d50", "#b4622c", "#8a8f8a"


def sign_test(successes: int, trials: int) -> float:
    """Two-sided probability of a split this lopsided under no preference."""
    if trials == 0:
        return 1.0
    k = max(successes, trials - successes)
    tail = sum(comb(trials, i) for i in range(k, trials + 1)) / 2 ** trials
    return min(1.0, 2 * tail)


def main() -> None:
    sessions = [json.loads(p.read_text()) for p in SESSIONS]
    by_id = [{a["id"]: a for a in s["answers"]} for s in sessions]
    report = {"n_raters": len(sessions)}

    print(f"{len(sessions)} rater session(s)\n")

    # ---- catch trials: is the instrument working at all? --------------------
    print("catch trials")
    catches = []
    for s in by_id:
        a = s["catch_clean"]
        ok = a["chose"] == "dino_clean"
        catches.append(ok)
        print(f"  clean vs scrambled -> {a['chose']}  {'PASS' if ok else 'FAIL'}"
              f"  ({a['ms']} ms)")
        b = s["catch_bothbad"]
        print(f"  scrambled vs L4_noise -> {b['chose']}  ({b['ms']} ms)")
    report["catch_pass"] = sum(catches)

    # ---- the ladder --------------------------------------------------------
    print("\niso-distance ladder: same shape distance, one feature destroyed")
    print(f"  {'rung':<6}{'distance':>9}{'choice':>12}{'ms':>7}")
    rows, merged_wins, decided = [], 0, 0
    for rung in LADDER:
        d = DINO[f"{rung}_merged"]["distance_from_clean"]
        for s in by_id:
            a = s[rung]
            choice = ("merged" if a["chose"].endswith("_merged")
                      else "noise" if a["chose"].endswith("_noise") else a["chose"])
            rows.append({"rung": rung, "distance": d, "choice": choice, "ms": a["ms"]})
            if choice in ("merged", "noise"):
                decided += 1
                merged_wins += choice == "merged"
            print(f"  {rung:<6}{d:9.3f}{choice:>12}{a['ms']:7d}")
    # The two repeats are decided judgements too, and excluding them would throw
    # away half the evidence to keep the table tidy.
    for rung in ("L2", "L4"):
        for s in by_id:
            a = s[f"{rung}_repeat"]
            if a["chose"].endswith("_merged") or a["chose"].endswith("_noise"):
                decided += 1
                merged_wins += a["chose"].endswith("_merged")
    p = sign_test(merged_wins, decided)
    print(f"\n  decided judgements (rungs + repeats): {decided}, "
          f"merged preferred in {merged_wins}  (sign test p = {p:.3f})")
    report["ladder"] = {"rows": rows, "decided": decided,
                        "merged_wins": merged_wins, "sign_test_p": p}

    # ---- repeats -----------------------------------------------------------
    print("\nself-consistency")
    agree = 0
    for rung in ("L2", "L4"):
        for s in by_id:
            first, again = s[rung]["chose"], s[f"{rung}_repeat"]["chose"]
            same = first == again
            agree += same
            print(f"  {rung}: {first} then {again}  {'same' if same else 'CHANGED'}")
    report["repeat_agreement"] = f"{agree}/{2 * len(by_id)}"

    # ---- text --------------------------------------------------------------
    print("\ntext, read BEFORE the answer appeared on the page")
    for key in ("read_outline", "read_stroke"):
        for s in by_id:
            a = s[key]
            print(f"  {a['image']:<22} -> {a['chose']:<8} ({a['ms']} ms)")

    print("\ntext, rated AFTER being told the word is LIT")
    text_rows = []
    for key in ("rate_outline_free", "rate_outline_upright",
                "rate_stroke_free", "rate_stroke_upright"):
        for s in by_id:
            a = s[key]
            metric = CONDITIONS[key.replace("rate_", "")]["distance"]
            text_rows.append({"image": a["image"], "metric": metric,
                              "rating": a["chose"], "ms": a["ms"]})
            print(f"  {a['image']:<22} metric {metric:.3f} -> {a['chose']}"
                  f"  ({a['ms']} ms)")
    for key in ("pair_outline", "pair_stroke"):
        for s in by_id:
            a = s[key]
            print(f"  {key}: {a['chose']}  ({a['ms']} ms)")
            text_rows.append({"pair": key, "chose": a["chose"], "ms": a["ms"]})
    report["text"] = text_rows

    # ---- figure ------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    xs = [DINO[f"{r}_merged"]["distance_from_clean"] for r in LADDER]
    choices = [next(r["choice"] for r in rows if r["rung"] == rung) for rung in LADDER]
    times = [next(r["ms"] for r in rows if r["rung"] == rung) for rung in LADDER]

    colors = [MERGED if c == "merged" else NOISE if c == "noise" else TIE
              for c in choices]
    ax1.bar(range(len(LADDER)), [1] * len(LADDER), color=colors, width=0.62)
    ax1.set_xticks(range(len(LADDER)))
    ax1.set_xticklabels([f"{r}\n{x:.3f}" for r, x in zip(LADDER, xs)])
    ax1.set_yticks([])
    ax1.set_ylim(0, 1.35)
    for i, c in enumerate(choices):
        label = {"merged": "feature\ndestroyed", "noise": "noise"}.get(c, "tie")
        ax1.text(i, 1.05, label, ha="center", va="bottom", fontsize=9, color=INK)
    ax1.set_title("Which is more dinosaur-like?\nboth members of each pair are the "
                  "same shape distance from clean", fontsize=10)
    ax1.set_xlabel("rung, and the shape distance both members share", fontsize=9)
    for s in ax1.spines.values():
        s.set_visible(False)

    ax2.plot(xs, times, "o-", color=INK, lw=1.6, ms=7)
    for x, t, c in zip(xs, times, choices):
        ax2.annotate(f"{t} ms", (x, t), textcoords="offset points",
                     xytext=(0, 9), ha="center", fontsize=9, color=INK)
    ax2.set_xlabel("shape distance (identical for both members)", fontsize=9)
    ax2.set_ylabel("decision time", fontsize=9)
    ax2.set_title("The metric calls all four pairs equally matched.\n"
                  "L1 took 6.7 s and ended in a tie; L4 took 1.1 s and did not.",
                  fontsize=10)
    ax2.set_ylim(0, max(times) * 1.35)
    ax2.grid(alpha=0.25, lw=0.6)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
