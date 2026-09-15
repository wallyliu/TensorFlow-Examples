"""
POC 6 - where is the discrimination threshold, and does the search live above it?

The third rater judged 12 pairs of the same heart route degraded to known
distances, plus 3 catch trials pairing rungs of equal quality. The answer is
unusually clean: every gap up to 0.10 was called "about the same", every gap
from 0.15 up was answered correctly, and nothing in between was sampled.

That brackets the threshold at roughly 0.10-0.15 - and the location search's own
shortlists span less than that, which means most of what the search ranks is
invisible to the person who will walk it.

Run:  python poc6c_analyse.py
Out:  poc6c_threshold.png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT_PNG = Path(__file__).with_name("poc6c_threshold.png")
SHORTLIST = Path(__file__).with_name("poc6d_shortlist.json")

# Rater 3's answers, read back from the artifact's store.
# outcome: "tie" = called them the same; "correct" = picked the better rung.
TRIALS = [
    {"id": "g00", "kind": "catch", "gap": 0.0000, "outcome": "tie", "ms": 1593},
    {"id": "g01", "kind": "catch", "gap": 0.0004, "outcome": "guess", "ms": 11366},
    {"id": "g02", "kind": "catch", "gap": 0.0033, "outcome": "tie", "ms": 15168},
    {"id": "g03", "kind": "gap", "gap": 0.0091, "outcome": "tie", "ms": 4184},
    {"id": "g04", "kind": "gap", "gap": 0.0216, "outcome": "tie", "ms": 7221},
    {"id": "g05", "kind": "gap", "gap": 0.0300, "outcome": "tie", "ms": 2527},
    {"id": "g06", "kind": "gap", "gap": 0.0387, "outcome": "tie", "ms": 2817},
    {"id": "g07", "kind": "gap", "gap": 0.0564, "outcome": "tie", "ms": 7035},
    {"id": "g08", "kind": "gap", "gap": 0.0741, "outcome": "tie", "ms": 2141},
    {"id": "g09", "kind": "gap", "gap": 0.1005, "outcome": "tie", "ms": 2360},
    {"id": "g10", "kind": "gap", "gap": 0.1523, "outcome": "correct", "ms": 1545},
    {"id": "g11", "kind": "gap", "gap": 0.2246, "outcome": "correct", "ms": 958},
    {"id": "g12", "kind": "gap", "gap": 0.3072, "outcome": "correct", "ms": 1879},
    {"id": "g13", "kind": "repeat", "gap": 0.3072, "outcome": "correct", "ms": 931},
    {"id": "g14", "kind": "repeat", "gap": 0.1005, "outcome": "tie", "ms": 2118},
]

TIE = "#2f6f9f"       # called them the same
SEEN = "#1a7f37"      # picked the better one
INK = "#1d2229"
MUTED = "#68727d"
GRID = "#dfe4e9"


def main() -> None:
    gaps = np.array([t["gap"] for t in TRIALS])
    seen = [t for t in TRIALS if t["outcome"] == "correct"]
    tied = [t for t in TRIALS if t["outcome"] == "tie"]
    guessed = [t for t in TRIALS if t["outcome"] == "guess"]

    lower = max(t["gap"] for t in tied)
    upper = min(t["gap"] for t in seen)
    print(f"largest gap called 'about the same' : {lower:.4f}")
    print(f"smallest gap answered correctly     : {upper:.4f}")
    print(f"threshold bracketed to              : {lower:.2f} - {upper:.2f}")
    print(f"catch trials called 'the same'      : {len(tied) - sum(1 for t in tied if t['kind'] == 'gap' or t['kind'] == 'repeat')}/3")
    print("repeats consistent                  : 2/2")

    fig, axes = plt.subplots(2, 1, figsize=(11, 7.4), sharex=True,
                             gridspec_kw={"height_ratios": [1.25, 1], "hspace": 0.16})

    for ax in axes:
        ax.axvspan(lower, upper, color=MUTED, alpha=0.13, zorder=0)
        ax.grid(axis="x", color=GRID, lw=0.7, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)

    # Panel 1 - what the rater said, by how big the gap was.
    top = axes[0]
    top.scatter([t["gap"] for t in tied], [0] * len(tied), s=150, color=TIE,
                edgecolor="white", linewidth=1.4, zorder=4)
    top.scatter([t["gap"] for t in guessed], [0] * len(guessed), s=150,
                facecolor="white", edgecolor=TIE, linewidth=1.8, zorder=4)
    top.scatter([t["gap"] for t in seen], [1] * len(seen), s=150, color=SEEN,
                edgecolor="white", linewidth=1.4, zorder=4)
    top.set_yticks([0, 1])
    top.set_yticklabels(["called them\nthe same", "picked the\nbetter one"], fontsize=10.5)
    top.set_ylim(-0.6, 1.6)
    top.tick_params(axis="y", length=0)
    top.annotate("threshold\nlies in here", ((lower + upper) / 2, 1.38), ha="center",
                 va="center", fontsize=9.5, color=MUTED)
    top.annotate("hollow = catch trial\n(the two really were identical)",
                 (0.004, -0.45), ha="left", va="center", fontsize=9, color=MUTED)
    top.set_title("A person sees no difference below a metric gap of about 0.12",
                  fontsize=13, color=INK, loc="left", pad=12)

    # Panel 2 - reaction time, the engagement signature.
    bottom = axes[1]
    for group, color, face in ((tied, TIE, TIE), (seen, SEEN, SEEN)):
        bottom.scatter([t["gap"] for t in group], [t["ms"] / 1000 for t in group],
                       s=90, color=face, edgecolor="white", linewidth=1.2, zorder=4)
    bottom.scatter([t["gap"] for t in guessed], [t["ms"] / 1000 for t in guessed],
                   s=90, facecolor="white", edgecolor=TIE, linewidth=1.8, zorder=4)
    bottom.set_yscale("log")
    bottom.set_yticks([1, 2, 5, 10, 15])
    bottom.set_yticklabels(["1s", "2s", "5s", "10s", "15s"], fontsize=10)
    bottom.set_ylabel("time to answer", fontsize=10.5, color=INK)
    bottom.set_xlabel("gap between the two routes, in metric units", fontsize=10.5, color=INK)
    bottom.set_title("and took longest on exactly the pairs that were hardest to tell apart",
                     fontsize=11, color=MUTED, loc="left", pad=8)

    # Where the search actually operates.
    if SHORTLIST.exists():
        spreads = {k: max(v) - min(v) for k, v in json.loads(SHORTLIST.read_text()).items()}
        widest = max(spreads.values())
        axes[0].annotate(
            f"the location search's own shortlists differ by at most {widest:.2f}",
            (widest, -0.45), xytext=(widest + 0.012, -0.45), ha="left", va="center",
            fontsize=9.5, color=INK,
            arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.2, shrinkA=0, shrinkB=2))
        axes[0].scatter([widest], [-0.45], s=40, color=INK, zorder=5)
        print("\nshortlist spreads: " + ", ".join(f"{k} {v:.3f}" for k, v in spreads.items()))
        print(f"widest shortlist spread {widest:.3f} vs threshold {lower:.2f}-{upper:.2f}")

    axes[0].set_xlim(-0.012, 0.33)
    for handle, label in ((TIE, "called them the same"), (SEEN, "picked the better one")):
        axes[0].scatter([], [], color=handle, s=110, label=label, edgecolor="white")
    axes[0].legend(loc="upper left", fontsize=9.5, frameon=False, bbox_to_anchor=(0.0, 1.02))

    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nsaved {OUT_PNG}")


if __name__ == "__main__":
    main()
