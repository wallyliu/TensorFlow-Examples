"""
Two ways to write a word on a map, and what each costs the rider.

`outline` traces both edges of every letter stroke - a printed letter.
`stroke` runs one line down the middle, from a 26-glyph single-stroke font,
and rides it out and back.

The expectation going in was that one line is the cheap option. It is not, and
the reason is simple enough to check without any metric: a line with no
thickness has to be ridden twice, so it costs 2x its length, while an outline
costs its perimeter - which for a thin letter is also about 2x the stroke
length. Measured at equal width the two come out within 7% of each other
(LIT 0.93, LOVE 1.05, TAIPEI 0.96). One line saves nothing.

What it does cost is legibility, and both the metric and the eye agree. n_min
rises 27-43% (LIT 84->120, LOVE 160->216, TAIPEI 240->304) and the pictures
show why: when every part of the drawing is a thin line, the connectors joining
the strokes are indistinguishable from the strokes themselves. In LIT the link
from the I's top bar to the T's top bar is collinear with both and fuses the two
letters into one shape. An outline does not have this problem - a connector
between two closed letterforms reads as a bridge because the letters are not
thin lines.

Kept as a user-selectable style anyway: it is legitimate to want it, and for
some non-text shapes the trade may go the other way.

Run:  python poc12_stroke_vs_outline.py
Out:  poc12_stroke_vs_outline.png, poc12_stroke_vs_outline.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import route_feasibility as rf
from multi_contour import text_curve
from poc11_onestroke import n_min_curve, perimeter

WORDS = ["LIT", "LOVE", "TAIPEI"]
STYLES = ["outline", "stroke"]
OUT_PNG = Path(__file__).with_name("poc12_stroke_vs_outline.png")
OUT_JSON = Path(__file__).with_name("poc12_stroke_vs_outline.json")


def measure(word: str, style: str, mode: str = "bike") -> dict:
    curve = text_curve(word, style)
    cfg = rf.MODES[mode]
    n = n_min_curve(curve)
    p = perimeter(curve)
    return {"curve": curve, "n_min": n, "perimeter": p,
            "width_km": n * cfg["street_scale_m"] / p / 1000.0,
            "km": n * cfg["street_scale_m"] * cfg["detour"] / 1000.0}


def main() -> None:
    results = {}
    fig, axes = plt.subplots(len(WORDS), len(STYLES),
                             figsize=(6 * len(STYLES), 2.6 * len(WORDS)))
    print(f"{'word':8}{'style':10}{'n_min':>7}{'width km':>10}{'bike km':>10}{'vs outline':>12}")
    for row, word in enumerate(WORDS):
        per_style = {s: measure(word, s) for s in STYLES}
        base = per_style["outline"]["km"]
        for col, style in enumerate(STYLES):
            m = per_style[style]
            saving = "" if style == "outline" else f"{(m['km'] / base - 1) * 100:+.0f}%"
            print(f"{word:8}{style:10}{m['n_min']:7d}{m['width_km']:10.1f}"
                  f"{m['km']:10.1f}{saving:>12}")
            results.setdefault(word, {})[style] = {
                k: v for k, v in m.items() if k != "curve"}

            ax = axes[row][col]
            c = m["curve"]
            ax.plot(c[:, 0], c[:, 1], lw=1.1, color="#2b6cb0")
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(f"{word} · {style} · n_min {m['n_min']} · "
                         f"{m['km']:.0f} km bike", fontsize=10)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=130)
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
