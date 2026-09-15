"""
Where does a route stop being recognisable?

BACKLOG #3, the oldest open item. 0.10 is the DISCRIMINATION threshold - where
a person sees that two routes differ. It has never been the pass mark for
"someone can tell what this is", and every artefact in this project that quotes
a band has been careful to say so. This measures the other number.

The instrument is POC 28's: the route alone with no reference, named from all
five shapes at once plus "none of these", options reshuffled every trial, no
feedback, no score. 30 items, six per shape, spread 0.069 to 0.540. Chance is
1/5.

Read the two failure modes separately. Picking the WRONG SHAPE is confusion -
the route looks like something, just not the right thing. Picking "none" is the
failure this is about: nothing is legible. They are pooled for the threshold,
because both mean the rider did not get the shape they asked for, but which one
dominates says what is actually going wrong.

Run:  python poc29_recognisability.py <responses.json> [...]
Out:  poc29_recognisability.png, poc29_recognisability.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

CHANCE = 0.20
OUT_PNG = Path(__file__).with_name("poc29_recognisability.png")
OUT_JSON = Path(__file__).with_name("poc29_recognisability.json")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Binomial interval that stays inside [0,1] at small n, unlike normal."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def load(paths) -> list:
    rows = []
    for path in paths:
        doc = json.loads(Path(path).read_text())
        answers = doc.get("answers") or doc.get("data", {}).get("answers") or []
        for a in answers:
            rows.append({**a, "rater": Path(path).stem})
    return rows


def main() -> None:
    paths = sys.argv[1:]
    if not paths:
        print(__doc__.strip().splitlines()[-3])
        return
    rows = load(paths)
    raters = sorted({r["rater"] for r in rows})
    d = np.array([r["distance"] for r in rows])
    ok = np.array([bool(r["correct"]) for r in rows])
    none = np.array([r["choice"] == "none" for r in rows])
    print(f"{len(rows)} judgements from {len(raters)} rater(s)")
    lo, hi = wilson(int(ok.sum()), len(ok))
    print(f"overall {ok.sum()}/{len(ok)} = {ok.mean():.0%} "
          f"[{lo:.0%}, {hi:.0%}]   chance {CHANCE:.0%}\n")

    edges = [0.0, 0.10, 0.16, 0.22, 0.32, 1.01]
    print(f"{'band':>12}{'n':>4}{'named right':>13}{'95% CI':>16}"
          f"{'wrong shape':>13}{'cannot tell':>13}")
    bands = []
    for a, b in zip(edges, edges[1:]):
        m = (d >= a) & (d < b)
        if not m.any():
            continue
        k, n = int(ok[m].sum()), int(m.sum())
        cl, ch = wilson(k, n)
        wrong = int((~ok[m] & ~none[m]).sum())
        cant = int(none[m].sum())
        print(f"{a:.2f}-{b if b <= 1 else 1:.2f}{n:>6}{k:>7}/{n:<5}"
              f"{f'[{cl:.0%}, {ch:.0%}]':>16}{wrong:>13}{cant:>13}")
        bands.append({"lo": a, "hi": min(b, 1.0), "n": n, "correct": k,
                      "ci": [cl, ch], "wrong_shape": wrong, "cannot_tell": cant})

    # Logistic fit, purely to read off where the curve crosses chance. Two
    # parameters on this much data is already generous; nothing richer is
    # justified and the interval below is what the estimate is worth.
    def nll(theta):
        a, b = theta
        p = CHANCE + (1 - CHANCE) / (1 + np.exp(-(a + b * d)))
        p = np.clip(p, 1e-9, 1 - 1e-9)
        return -(ok * np.log(p) + (~ok) * np.log(1 - p)).sum()

    from scipy.optimize import minimize
    best = minimize(nll, [3.0, -10.0], method="Nelder-Mead")
    a, b = best.x
    # Halfway between chance and ceiling: the conventional threshold point.
    thr = -a / b if b != 0 else float("nan")
    print(f"\nlogistic fit: halfway point at distance {thr:.3f}")

    boot = []
    rng = np.random.default_rng(0)
    for _ in range(2000):
        idx = rng.integers(0, len(d), len(d))
        try:
            r = minimize(lambda t: -(lambda p: (ok[idx] * np.log(p)
                                                + (~ok[idx]) * np.log(1 - p)).sum())(
                np.clip(CHANCE + (1 - CHANCE) / (1 + np.exp(-(t[0] + t[1] * d[idx]))),
                        1e-9, 1 - 1e-9)), [3.0, -10.0], method="Nelder-Mead")
            if r.x[1] != 0:
                boot.append(-r.x[0] / r.x[1])
        except Exception:      # noqa: BLE001 - a degenerate resample is not a bug
            continue
    boot = np.array([x for x in boot if 0 < x < 1.5])
    if len(boot) > 100:
        blo, bhi = np.percentile(boot, [2.5, 97.5])
        print(f"bootstrap 95%: {blo:.3f} to {bhi:.3f}   ({len(boot)} resamples)")
    else:
        blo = bhi = float("nan")

    per_shape = {}
    for shape in sorted({r["shape"] for r in rows}):
        m = np.array([r["shape"] == shape for r in rows])
        per_shape[shape] = {"n": int(m.sum()), "correct": int(ok[m].sum())}
    print("\nby shape: " + "  ".join(
        f"{s} {v['correct']}/{v['n']}" for s, v in per_shape.items()))

    result = {"n": len(rows), "raters": raters, "accuracy": float(ok.mean()),
              "chance": CHANCE, "bands": bands, "threshold": float(thr),
              "threshold_ci": [float(blo), float(bhi)],
              "per_shape": per_shape,
              "wrong_shape_total": int((~ok & ~none).sum()),
              "cannot_tell_total": int(none.sum())}
    OUT_JSON.write_text(json.dumps(result, indent=2))

    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    xs = np.linspace(0, 0.6, 200)
    ax.plot(xs, CHANCE + (1 - CHANCE) / (1 + np.exp(-(a + b * xs))),
            lw=2, color="#2f5d50", zorder=2)
    for bd in bands:
        mid = (bd["lo"] + bd["hi"]) / 2
        p = bd["correct"] / bd["n"]
        ax.errorbar(mid, p, yerr=[[p - bd["ci"][0]], [bd["ci"][1] - p]],
                    fmt="o", ms=7, color="#191b1a", ecolor="#9aa09c",
                    capsize=4, lw=1.2, zorder=3)
    ax.axhline(CHANCE, ls="--", lw=1, color="#b4622c")
    ax.annotate("亂猜 20%", (0.60, CHANCE + 0.02), ha="right", fontsize=9,
                color="#b4622c")
    ax.axvline(0.10, ls=":", lw=1, color="#888")
    ax.annotate("0.10", (0.105, 0.03), fontsize=9, color="#666")
    if np.isfinite(thr):
        ax.axvline(thr, ls="-", lw=1.2, color="#9a3b1f", alpha=.6)
    ax.set_xlim(0, 0.6); ax.set_ylim(0, 1.02)
    ax.set_xlabel("shape distance")
    ax.set_ylabel("named correctly")
    ax.set_title("Recognition against shape distance", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT_PNG, dpi=140)
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
