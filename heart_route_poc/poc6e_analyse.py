"""
POC 6 - reconciling the two threshold runs.

Version 2 fixed version 1's missing response option and sampled the interval
version 1 never reached. It also contradicted version 1 outright: on essentially
the same comparison - the clean route against one about 0.16 away - version 1
answered "about the same" twice, and version 2 answered correctly in 0.85 s.

The reaction times explain it. Version 2's own answers split into two regimes
with nothing in between:

    gap <= 0.074   7-13 SECONDS, and one of the two was still called a tie
    gap >= 0.098   under 1.4 s, every one correct

An eight-fold cliff in response time at the same place the accuracy turns. So
discrimination below ~0.10 is not impossible, it is EFFORTFUL - and version 2
made effort cheaper in a way that does not generalise: every one of its 14 trials
put the SAME clean route on one side, so "find the smooth one" becomes a
learnable strategy. A person glancing at one route on a map has no reference to
compare against and no practice. That is version 1's condition, and version 1
tied everything up to 0.10.

Fixing one confound introduced another. The honest reading takes what both runs
agree on: **effortless discrimination begins around 0.10**, and that is the
number a product should use, because nobody stares at a map for thirteen seconds.

Run:  python poc6e_analyse.py
Out:  poc6e_threshold_v2.png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT_PNG = Path(__file__).with_name("poc6e_threshold_v2.png")
SHORTLIST = Path(__file__).with_name("poc6d_shortlist.json")

# Version 1: unanchored pairs, three response options. Contaminated trials
# (a tie where neither route was a clean heart) are excluded - see README.
V1 = [(0.0000, "tie"), (0.0216, "tie"), (0.0387, "tie"), (0.0741, "tie"),
      (0.1005, "tie"), (0.1005, "tie"), (0.1523, "correct"), (0.2246, "correct"),
      (0.3072, "correct"), (0.3072, "correct")]

# Version 2: every pair anchored to the clean route, four response options.
V2 = [(0.0000, "tie", 1930), (0.0150, "tie", 3366), (0.0486, "correct", 6981),
      (0.0741, "tie", 13325), (0.0982, "correct", 848), (0.1095, "correct", 1037),
      (0.1203, "correct", 1029), (0.1203, "correct", 987), (0.1306, "correct", 889),
      (0.1306, "correct", 830), (0.1501, "correct", 672), (0.1679, "correct", 751),
      (0.2200, "correct", 783), (0.2987, "correct", 1343)]

EFFORTLESS = 0.098   # fastest correct answer; the top of the reaction-time cliff
EFFORTFUL = 0.0741   # slowest trial, still answered "about the same"

V1_COLOR = "#2f6f9f"
V2_COLOR = "#1a7f37"
INK = "#1d2229"
MUTED = "#68727d"
GRID = "#dfe4e9"


def main() -> None:
    fig, axes = plt.subplots(2, 1, figsize=(11, 7.8), sharex=True,
                             gridspec_kw={"height_ratios": [1.1, 1], "hspace": 0.18})
    for ax in axes:
        ax.axvspan(EFFORTFUL, EFFORTLESS, color=MUTED, alpha=0.13, zorder=0)
        ax.grid(axis="x", color=GRID, lw=0.7, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)

    top = axes[0]
    for data, colour, offset, label in ((V1, V1_COLOR, 0.08, "run 1 — no reference, 3 options"),
                                        (V2, V2_COLOR, -0.08, "run 2 — every pair anchored, 4 options")):
        for row in data:
            gap, outcome = row[0], row[1]
            y = (1 if outcome == "correct" else 0) + offset
            top.scatter([gap], [y], s=135, color=colour, edgecolor="white",
                        linewidth=1.4, zorder=4)
        top.scatter([], [], s=120, color=colour, label=label, edgecolor="white")
    top.set_yticks([0, 1])
    top.set_yticklabels(["called them\nthe same", "picked the\nbetter one"], fontsize=10.5)
    top.set_ylim(-0.65, 1.65)
    top.tick_params(axis="y", length=0)
    top.legend(loc="center left", fontsize=9.5, frameon=False, bbox_to_anchor=(0.015, 0.5))
    top.set_title("The two runs disagree exactly where the task stops being effortless",
                  fontsize=13, color=INK, loc="left", pad=12)
    # The two runs' answers to the same comparison sit one above the other at
    # ~0.10; label the pair from the right so it clears the legend.
    top.annotate("same comparison,\nopposite answers", (0.108, 1.32), ha="left",
                 va="center", fontsize=9.5, color=MUTED)
    top.annotate("", (0.1005, 1.08), (0.1055, 1.28),
                 arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.9))
    top.annotate("", (0.0982, 0.12), (0.1055, 1.26),
                 arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.9))

    bottom = axes[1]
    quick = [r for r in V2 if r[2] < 5000]
    slow = [r for r in V2 if r[2] >= 5000]
    bottom.scatter([r[0] for r in quick], [r[2] / 1000 for r in quick], s=95,
                   color=V2_COLOR, edgecolor="white", linewidth=1.2, zorder=4)
    bottom.scatter([r[0] for r in slow], [r[2] / 1000 for r in slow], s=95,
                   color=V2_COLOR, edgecolor="white", linewidth=1.2, zorder=4)
    bottom.set_yscale("log")
    bottom.set_yticks([0.7, 1, 2, 5, 10, 15])
    bottom.set_yticklabels(["0.7s", "1s", "2s", "5s", "10s", "15s"], fontsize=10)
    bottom.set_ylabel("time to answer (run 2)", fontsize=10.5, color=INK)
    bottom.set_xlabel("gap from the clean route, in metric units", fontsize=10.5, color=INK)
    bottom.annotate("7–13 s of staring", (0.056, 9.0), ha="center", fontsize=9.5, color=MUTED)
    bottom.annotate("under 1.4 s, every one correct", (0.19, 1.75), ha="center",
                    fontsize=9.5, color=MUTED)
    bottom.set_title("An eight-fold cliff in effort at the same gap", fontsize=11,
                     color=MUTED, loc="left", pad=8)

    if SHORTLIST.exists():
        spreads = {k: max(v) - min(v) for k, v in json.loads(SHORTLIST.read_text()).items()}
        # star5 (0.134) and triangle (0.137) would print on top of each other,
        # so shapes closer than 0.01 apart share one tick and one label.
        ordered = sorted(spreads.items(), key=lambda kv: kv[1])
        grouped: list[tuple[list[str], float]] = []
        for name, spread in ordered:
            if grouped and spread - grouped[-1][1] < 0.01:
                grouped[-1][0].append(name)
            else:
                grouped.append(([name], spread))
        for names, spread in grouped:
            top.annotate("", (spread, -0.52), (spread, -0.34),
                         arrowprops=dict(arrowstyle="-", color=INK, lw=1.0))
            top.annotate(" · ".join(names), (spread, -0.60), ha="center", va="top",
                         fontsize=8.6, color=INK)
        top.annotate("how far apart the search's own shortlist runs:", (0.0, -0.34),
                     ha="left", va="bottom", fontsize=9, color=MUTED)
        print("shortlist spreads: " + ", ".join(f"{k} {v:.3f}" for k, v in spreads.items()))
        for name, spread in spreads.items():
            verdict = ("invisible" if spread < EFFORTFUL else
                       "effortful only" if spread < EFFORTLESS else "visible at a glance")
            print(f"  {name:<10}{spread:.3f}  ->  {verdict}")

    axes[0].set_xlim(-0.012, 0.32)
    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nsaved {OUT_PNG}")


if __name__ == "__main__":
    main()
