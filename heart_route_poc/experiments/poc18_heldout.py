"""
The held-out test of the wander term, and what it actually settles.

POC 15 fitted one constant (0.7) to four rungs of one shape and used it to
predict a DIFFERENT pattern for each of three shapes it had never seen: the
heart crossing the discrimination threshold only at its last rung, the crescent
never crossing it, the star past it from the first. That is what made this a
test rather than a demonstration - always picking one side fails two of three,
always answering "about the same" fails two of three.

Two raters. Catches 6/6, repeats 6/6, and they agreed with each other on 11 of
12 trials, so what follows is not one person's noise.

DIRECTION: confirmed, hard. Seventeen of seventeen decided judgements prefer the
member with a feature destroyed over noise at the same shape distance
(p < 0.0001), on shapes chosen for being unlike the dinosaur the term came from.

CALIBRATION: fails. 7 of 24 predictions right. The model expected a tie in 18 of
the 24; the raters tied twice.

And it cannot be rescued by retuning. Every "merged" answer is a lower bound on
the weight and every "tie" an upper bound. BOTH raters answered "merged" on
crescent L1 (wander gap 0.024, needing w > 4.1) and "tie" on heart L1 (gap
0.039, needing w < 2.6). No constant satisfies both, so the weighted-sum FORM is
what fails, not the 0.7 - and it now rests on two people agreeing rather than on
one person's two clicks.

What the answers look like instead is closer to lexicographic than graded: a
crescent with a horn sliced off beats one that wobbles everywhere, at a gap a
sixth of the supposed threshold, in under three seconds. "Neither" appears only
at the top of the ladders, where both members are past saving.

Run:  python poc18_heldout.py
Out:  poc18_heldout.png, poc18_heldout.json
"""

from __future__ import annotations

import json
from math import comb
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
WIGGLE = json.loads((HERE / "poc15_wiggle.json").read_text())
OUT_PNG = HERE / "poc18_heldout.png"
OUT_JSON = HERE / "poc18_heldout.json"

SHAPES = ["heart", "crescent", "star5"]
RUNGS = ["L1", "L2", "L3", "L4"]
LABEL = {"heart": "heart", "crescent": "crescent", "star5": "star"}


def sign_test(successes: int, trials: int) -> float:
    if trials == 0:
        return 1.0
    k = max(successes, trials - successes)
    return min(1.0, 2 * sum(comb(trials, i) for i in range(k, trials + 1)) / 2 ** trials)


def side(choice: str) -> str:
    if choice.endswith("_merged"):
        return "merged"
    if choice.endswith("_noise"):
        return "noise"
    return choice          # "tie" or "neither"


def main() -> None:
    paths = sorted((HERE / "rater/v3/sessions").glob("*.json"))
    sessions = [json.loads(p.read_text()) for p in paths]
    print(f"{len(sessions)} session(s)\n")

    report = {"n_raters": len(sessions), "shapes": {}}
    predicted_right = total = 0
    decided = merged_wins = 0
    rows = []

    for shape in SHAPES:
        print(f"=== {shape}")
        print(f"  {'rung':<5}{'distance':>9}{'v2 gap':>9}{'predicted':>11}"
              + "".join(f"{'r' + str(i + 1):>10}" for i in range(len(sessions))))
        report["shapes"][shape] = []
        for rung in RUNGS:
            info = next(r for r in WIGGLE["shapes"][shape]["rungs"]
                        if r["rung"] == rung)
            gap = info["v2_noise"] - info["v2_merged"]
            predicted = "merged" if gap > WIGGLE["discrimination_threshold"] else "tie"
            answers = [side(s_by_id[f"{shape}_{rung}"]["chose"])
                       for s_by_id in by_id]
            for a in answers:
                total += 1
                predicted_right += (a == predicted)
                if a in ("merged", "noise"):
                    decided += 1
                    merged_wins += a == "merged"
            rows.append({"shape": shape, "rung": rung, "gap": gap,
                         "distance": info["shape_distance"],
                         "predicted": predicted, "answers": answers})
            report["shapes"][shape].append(rows[-1])
            print(f"  {rung:<5}{info['shape_distance']:9.3f}{gap:9.3f}"
                  f"{predicted:>11}" + "".join(f"{a:>10}" for a in answers))
        print()

    print(f"predictions right: {predicted_right}/{total}")
    p = sign_test(merged_wins, decided)
    print(f"decided judgements: {decided}, feature-destroyed preferred "
          f"{merged_wins}  (sign test p = {p:.4f})")

    counts = {}
    for s_by_id in by_id:
        for shape in SHAPES:
            for rung in RUNGS:
                c = side(s_by_id[f"{shape}_{rung}"]["chose"])
                counts[c] = counts.get(c, 0) + 1
    print(f"answer mix: {counts}")

    catches = [s_by_id[f"{shape}_catch"]["chose"].endswith("_clean")
               for s_by_id in by_id for shape in SHAPES]
    print(f"catch trials passed: {sum(catches)}/{len(catches)}")

    repeats = [(s_by_id[f"{shape}_L3"]["chose"], s_by_id[f"{shape}_L3_repeat"]["chose"])
               for s_by_id in by_id for shape in SHAPES]
    agree = sum(a == b for a, b in repeats)
    print(f"repeat agreement: {agree}/{len(repeats)}")

    # Can ANY single weight reproduce these answers? Each "merged" answer says
    # the weighted wander gap cleared the threshold, each "tie" says it did not,
    # so every trial is one inequality on w. If the lower bounds cross the upper
    # bounds, no constant exists and the linear form itself is wrong - which is
    # a stronger statement than "0.7 was the wrong number".
    threshold = WIGGLE["discrimination_threshold"]
    lower, upper = [], []
    for r in rows:
        info = next(x for x in WIGGLE["shapes"][r["shape"]]["rungs"]
                    if x["rung"] == r["rung"])
        gap = info["wander_noise"] - info["wander_merged"]
        for a in r["answers"]:
            if a == "merged":
                lower.append(threshold / gap)
            elif a == "tie":
                upper.append(threshold / gap)
    bound = {"needs_w_above": max(lower) if lower else None,
             "needs_w_below": min(upper) if upper else None}
    bound["satisfiable"] = (bound["needs_w_above"] is None
                            or bound["needs_w_below"] is None
                            or bound["needs_w_above"] < bound["needs_w_below"])
    print(f"\na single weight would need w > {bound['needs_w_above']:.1f} "
          f"and w < {bound['needs_w_below']:.1f}: "
          f"{'satisfiable' if bound['satisfiable'] else 'IMPOSSIBLE'}")
    print(f"  (the bounds come from crescent L1 and heart L1, "
          f"answered the same way by all {len(by_id)} rater(s))")

    report.update(weight_bounds=bound,
                  predictions_right=f"{predicted_right}/{total}",
                  decided=decided, merged_wins=merged_wins, sign_test_p=p,
                  answer_mix=counts, catches=f"{sum(catches)}/{len(catches)}",
                  repeat_agreement=f"{agree}/{len(repeats)}")

    fig, axes = plt.subplots(1, len(SHAPES), figsize=(4.0 * len(SHAPES), 3.9),
                             sharey=True)
    colour = {"merged": "#2f5d50", "noise": "#b4622c",
              "tie": "#8a8f8a", "neither": "#7b4a8a"}
    for ax, shape in zip(np.atleast_1d(axes), SHAPES):
        sub = [r for r in rows if r["shape"] == shape]
        gaps = [r["gap"] for r in sub]
        for i, r in enumerate(sub):
            for j, a in enumerate(r["answers"]):
                ax.scatter(r["gap"], j, s=90, color=colour.get(a, "#000"), zorder=3)
            ax.annotate(r["rung"], (r["gap"], -0.55), ha="center", fontsize=8,
                        color="#6d716d")
        ax.axvline(WIGGLE["discrimination_threshold"], color="#c9c6bd", ls="--", lw=1)
        ax.set_xlim(min(gaps) - 0.05, max(gaps) + 0.05)
        ax.set_ylim(-0.9, max(1.0, len(sessions) - 0.2))
        ax.set_yticks([])
        ax.set_title(LABEL[shape], fontsize=10)
        ax.set_xlabel("v2 gap  (model predicts a preference\nright of the dashed line)",
                      fontsize=9)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
    handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=k)
               for k, c in colour.items()]
    np.atleast_1d(axes)[0].legend(handles=handles, frameon=False, fontsize=8,
                                  loc="upper left")
    fig.suptitle("The model predicts ties left of the line. The rater almost never tied.",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


paths = sorted((HERE / "rater/v3/sessions").glob("*.json"))
by_id = [{a["id"]: a for a in json.loads(p.read_text())["answers"]} for p in paths]

if __name__ == "__main__":
    main()
