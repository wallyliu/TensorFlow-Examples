"""
Can a drawing be judged before it is ridden?

`recognition.OBSERVED` is a table of what raters said, and POC 39 showed that
table beats every route-level measure this project has. It has one hole: a
shape nobody has rated gets no number at all, and six of the 33 on the page are
in that position. Drawing more shapes makes the hole bigger, not smaller.

`legibility.resolution_error` is a candidate prior. It is a property of the
DRAWING, the width and the city - no network, no fitting - and it says how much
of the figure lives below the scale a street network can resolve. If it
predicts which shapes people name, it can stand in for a rater round on a new
shape; if it does not, it is another measurement that flatters itself.

TWO QUESTIONS, and the second is the one that matters:

    per answer   does it beat distance and excursion at predicting one
                 judgement (the POC 39 comparison, with this added)
    per drawing  does it predict a SHAPE's named rate across the 27 rated
                 drawings - which is what a prior for an unrated shape means

Run:  python -m experiments.poc40_legibility
Out:  results/poc40_legibility.json
"""

from __future__ import annotations

import json

import numpy as np
from scipy.stats import spearmanr

import routeshape.feasibility as rf
import routeshape.street_scale as ss
from experiments.poc39_recalibrate import (RESULTS, cross_validated, fill_excursion,
                                           install_everything, load,
                                           current_drawing_only, logistic_fit)
from routeshape.legibility import resolution_error

MODE, LAT, LON = "bike", 25.0400, 121.5400
OUT = RESULTS / "poc40_legibility.json"


def widths(rows: list, scale: float) -> dict:
    """The width each round drew each shape at, from its own stimuli file."""
    out: dict = {}
    for n in sorted({r["round"] for r in rows}):
        for s in json.loads((RESULTS / f"poc{n}_stimuli.json").read_text()):
            if s.get("width_m"):
                out[(n, s["shape"])] = float(s["width_m"])
            elif s.get("target_km"):
                plan = rf.plan(s["shape"], float(s["target_km"]), MODE, scale)
                if plan.feasible:
                    out[(n, s["shape"])] = float(plan.width_m)
    return out


def main() -> None:
    install_everything()
    scale = ss.scale_for(LAT, LON, MODE, rf.MODES[MODE]["street_scale_m"])
    rows, _ = current_drawing_only(load())
    fill_excursion(rows)
    rows = [r for r in rows if r["excursion"] is not None]
    width = widths(rows, scale)
    kept = []
    for r in rows:
        w = width.get((r["round"], r["drawing"]))
        if w is None:
            continue
        r["width_m"] = w
        r["resolution"] = resolution_error(r["drawing"], w, scale)
        kept.append(r)
    rows = kept
    print(f"{len(rows)} answers over {len({r['drawing'] for r in rows})} drawings; "
          f"street scale {scale:.0f} m\n")

    y = np.array([float(r["correct"]) for r in rows])
    floor = np.array([1.0 / r["options"] for r in rows])
    ones = np.ones((len(rows), 1))
    dist = np.array([r["distance"] for r in rows])
    exc = np.array([r["excursion"] for r in rows])
    res = np.array([r["resolution"] for r in rows])
    names = sorted({r["drawing"] for r in rows})
    hot = np.zeros((len(rows), len(names)))
    for i, r in enumerate(rows):
        hot[i, names.index(r["drawing"])] = 1.0

    models = {
        "none": ones,
        "distance": np.column_stack([ones, dist]),
        "excursion": np.column_stack([ones, exc]),
        "resolution": np.column_stack([ones, res]),
        "resolution+excursion": np.column_stack([ones, res, exc]),
        "drawing": hot,
        "drawing+resolution": np.column_stack([hot, res]),
    }
    print(f"{'model':22s} {'cv logloss':>11s}")
    fits = {}
    for name, X in models.items():
        fits[name] = {"cv": cross_validated(y, X, floor)}
        print(f"{name:22s} {fits[name]['cv']:11.4f}")

    # --- the question that matters -----------------------------------------
    print("\nper drawing: resolution floor against the rate people named it")
    per = {}
    for n in names:
        g = [r for r in rows if r["drawing"] == n]
        per[n] = {"named": sum(r["correct"] for r in g), "shown": len(g),
                  "resolution": round(float(np.mean([r["resolution"] for r in g])), 4),
                  "width_m": round(float(np.mean([r["width_m"] for r in g]))),
                  "excursion": round(float(np.mean([r["excursion"] for r in g])), 4)}
    strong = {k: v for k, v in per.items() if v["shown"] >= 3}
    xs = np.array([v["resolution"] for v in strong.values()])
    ys = np.array([v["named"] / v["shown"] for v in strong.values()])
    rho, p = spearmanr(xs, ys)
    print(f"  {len(strong)} drawings seen 3+ times: Spearman {rho:+.3f}, p = {p:.3f}")
    xe = np.array([v["excursion"] for v in strong.values()])
    rho_e, p_e = spearmanr(xe, ys)
    print(f"  (excursion, same set:            Spearman {rho_e:+.3f}, p = {p_e:.3f})")
    for n in sorted(strong, key=lambda k: strong[k]["resolution"]):
        v = strong[n]
        print(f"  {n:16s} floor {v['resolution']:.4f}  "
              f"{v['named']:2d}/{v['shown']:2d}  {v['width_m']:5d} m wide")

    OUT.write_text(json.dumps({"models": fits, "per_drawing": per,
                               "spearman_resolution": [rho, p],
                               "spearman_excursion": [rho_e, p_e]},
                              ensure_ascii=False, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
