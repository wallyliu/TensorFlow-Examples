"""
What actually predicts whether a person names the route - and what the service
should therefore be telling them.

`recognition.py` maps `shape_distance` to a recognition rate through a logistic
curve fitted in POC 29, and `server/app.py` reports the result as "應該認得出
來". Four rounds since have pulled that apart:

  POC 32  recognition is a property of the DRAWING, not of the distance
          (permutation p < 0.0001)
  POC 35  excursion separates named from not-named where distance does not
  POC 36  a traced cactus at distance 0.300 was named; a hand-drawn elephant
          at 0.066 was not
  POC 37  OpenMoji's house at 0.196 unnamed, the hand-drawn gear at 0.124 named
          by all three raters

So the service is quoting a number built on a predictor the project has since
shown does not work. This pools every answer collected and asks which model of
the data deserves to be in the product, by AIC:

    none      one rate for everything - the null
    distance  a slope on shape_distance          <- what ships today
    excursion a slope on excursion
    both      both slopes
    drawing   one rate per drawing, no distance at all
    drawing+  per-drawing rate plus an excursion slope

The honest outcome may well be `drawing`: that there is no curve, and what the
page should say is "three of three people named this shape" or "nobody has
looked at this one yet". A model that fits worse than a lookup table is not a
model.

POC 32 and 33 did not record excursion - it did not exist yet - so it is
recomputed from the stored route. That reproduces the recorded value on POC 36
and 37 to a mean absolute error of 0.004-0.008, because the stored route is
subsampled to 220 points and a maximum is blunted by subsampling. The noise
attenuates any real relationship, so a weak result from the pooled fit is
ambiguous and a strong one is not.

Run:  python -m experiments.poc39_recalibrate
Out:  results/poc39_recalibrate.json
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

import routeshape.shapes.emoji as emoji
import routeshape.shapes.openmoji as openmoji
import routeshape.shapes.pack as pack
from routeshape.metrics import excursion
from routeshape.paths import RESULTS
from routeshape.shapes.library import SHAPES, resample_by_arclength

ROUNDS = (32, 33, 36, 37)
WELL_SAMPLED = 6      # answers before a per-drawing rate is worth fitting
OUT = RESULTS / "poc39_recalibrate.json"


def install_everything() -> None:
    """Every drawing any round has shown, including the retired ones."""
    pack.install()
    emoji.install()
    openmoji.install()
    import routeshape.shapes.library as sl
    for name, fn in pack.RETIRED.items():
        if name not in SHAPES:
            sl.register(name, fn())


def load() -> list:
    """One row per answer, across every round."""
    rows = []
    for n in ROUNDS:
        task = RESULTS / f"poc{n}_task.html"
        answers_dir = RESULTS / f"poc{n}_responses"
        if not task.exists() or not answers_dir.exists():
            continue
        data = json.loads(re.search(r"var DATA = (\{.*?\});\n",
                                    task.read_text(), re.S).group(1))
        meta = {i["id"]: i for i in data["items"]}
        options = len(data["options"])
        for f in sorted(answers_dir.rglob("*.json")):
            doc = json.loads(f.read_text())
            for a in doc.get("answers", []):
                item = meta.get(a["item"])
                if item is None:
                    continue
                rows.append({
                    "round": n, "session": doc.get("session", f.stem),
                    "item": a["item"],
                    "drawing": item.get("drawing", item["shape"]),
                    "arm": item.get("arm", "hand"),
                    "distance": float(item["distance"]),
                    "excursion": item.get("excursion"),
                    "route_km": item.get("route_km"),
                    "options": options,
                    "correct": bool(a["correct"]),
                    "blank": a["chosen"] == "__none__",
                    "xy": item["xy"],
                })
    return rows


def fill_excursion(rows: list) -> tuple[int, float]:
    """Recompute the missing excursions, and say how well that reproduces the
    ones that were recorded."""
    cache: dict = {}
    check = []
    filled = 0
    for r in rows:
        name = r["drawing"]
        if name not in SHAPES:
            continue
        if name not in cache:
            dense = resample_by_arclength(name, 4000)
            cache[name] = np.vstack([dense, dense[:1]])
        got = float(excursion(np.array(r["xy"]), cache[name]))
        if r["excursion"] is None:
            r["excursion"] = round(got, 4)
            r["excursion_recomputed"] = True
            filled += 1
        else:
            check.append(abs(got - r["excursion"]))
            r["excursion_recomputed"] = False
    return filled, float(np.mean(check)) if check else float("nan")


def logistic_fit(y: np.ndarray, X: np.ndarray, floor: np.ndarray):
    """Logistic regression with a per-row chance floor, by direct likelihood.

    The floor matters: a rater picking blind from fifteen options is right 7% of
    the time, and a model that can drive the predicted rate to zero will spend
    its parameters fitting that impossible region.
    """
    def neg_ll(beta):
        p = floor + (1 - floor) / (1 + np.exp(-np.clip(X @ beta, -40, 40)))
        p = np.clip(p, 1e-9, 1 - 1e-9)
        return -float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))

    best = None
    for seed in (0.0, 1.0, -1.0):
        start = np.full(X.shape[1], seed)
        res = minimize(neg_ll, start, method="Nelder-Mead",
                       options={"maxiter": 20000, "xatol": 1e-8, "fatol": 1e-8})
        if best is None or res.fun < best.fun:
            best = res
    return best.x, -best.fun


def main() -> None:
    install_everything()
    rows = load()
    if not rows:
        print("no answers found")
        return
    filled, agreement = fill_excursion(rows)
    rows = [r for r in rows if r["excursion"] is not None]
    y = np.array([float(r["correct"]) for r in rows])
    floor = np.array([1.0 / r["options"] for r in rows])
    dist = np.array([r["distance"] for r in rows])
    exc = np.array([r["excursion"] for r in rows])
    names = sorted({r["drawing"] for r in rows})
    index = {n: i for i, n in enumerate(names)}
    onehot = np.zeros((len(rows), len(names)))
    for i, r in enumerate(rows):
        onehot[i, index[r["drawing"]]] = 1.0
    ones = np.ones((len(rows), 1))

    sessions = sorted({(r["round"], r["session"]) for r in rows})
    print(f"{len(rows)} answers, {len(sessions)} rater-sessions, "
          f"{len(names)} drawings, rounds {sorted({r['round'] for r in rows})}")
    print(f"named {int(y.sum())}/{len(y)} = {y.mean():.0%}; "
          f"{filled} excursions recomputed "
          f"(agreement on the recorded ones: {agreement:.4f} mean abs error)\n")

    models = {
        "none": ones,
        "distance": np.column_stack([ones, dist]),
        "excursion": np.column_stack([ones, exc]),
        "both": np.column_stack([ones, dist, exc]),
        "drawing": onehot,
        "drawing+excursion": np.column_stack([onehot, exc]),
    }
    out = {}
    print(f"{'model':20s} {'params':>6s} {'logL':>9s} {'AIC':>9s} {'dAIC':>7s}")
    fits = {}
    for name, X in models.items():
        beta, ll = logistic_fit(y, X, floor)
        aic = 2 * X.shape[1] - 2 * ll
        fits[name] = {"logL": ll, "aic": aic, "params": X.shape[1],
                      "beta": [round(float(b), 4) for b in beta]}
    best_aic = min(f["aic"] for f in fits.values())
    for name, f in fits.items():
        print(f"{name:20s} {f['params']:6d} {f['logL']:9.2f} {f['aic']:9.2f} "
              f"{f['aic'] - best_aic:7.2f}")
        out[name] = f
    winner = min(fits, key=lambda k: fits[k]["aic"])
    print(f"\nbest by AIC: {winner}")

    # A per-drawing rate has one parameter per drawing and half the drawings
    # here were seen once or twice, where it fits them EXACTLY. AIC charges for
    # that but the comparison is still flattering, so run it again on the
    # drawings with enough answers to have a rate worth estimating.
    counts: dict = {}
    for r in rows:
        counts[r["drawing"]] = counts.get(r["drawing"], 0) + 1
    keep = [i for i, r in enumerate(rows) if counts[r["drawing"]] >= WELL_SAMPLED]
    kept_names = sorted({rows[i]["drawing"] for i in keep})
    print(f"\nagain on the {len(kept_names)} drawings with at least "
          f"{WELL_SAMPLED} answers ({len(keep)} answers):")
    sub_index = {n: i for i, n in enumerate(kept_names)}
    sub_hot = np.zeros((len(keep), len(kept_names)))
    for row, i in enumerate(keep):
        sub_hot[row, sub_index[rows[i]["drawing"]]] = 1.0
    sub_ones = np.ones((len(keep), 1))
    sub = {
        "none": sub_ones,
        "distance": np.column_stack([sub_ones, dist[keep]]),
        "excursion": np.column_stack([sub_ones, exc[keep]]),
        "drawing": sub_hot,
        "drawing+excursion": np.column_stack([sub_hot, exc[keep]]),
    }
    sub_fits = {}
    for name, X in sub.items():
        beta, ll = logistic_fit(y[keep], X, floor[keep])
        sub_fits[name] = {"logL": ll, "aic": 2 * X.shape[1] - 2 * ll,
                          "params": X.shape[1],
                          "beta": [round(float(b), 4) for b in beta]}
    sub_best = min(f["aic"] for f in sub_fits.values())
    for name, f in sub_fits.items():
        print(f"  {name:20s} {f['params']:4d} {f['logL']:9.2f} {f['aic']:9.2f} "
              f"{f['aic'] - sub_best:7.2f}")
    out["well_sampled"] = sub_fits
    out["well_sampled_drawings"] = kept_names

    # What the excursion slope means in the only units anybody can act on.
    slope = fits["drawing+excursion"]["beta"][-1]
    print(f"\nexcursion slope within a drawing: {slope:.1f} in log-odds per 1.0"
          f" of excursion, so +0.01 multiplies the odds of being named by "
          f"{math.exp(slope * 0.01):.2f}")

    # Whatever the curve says, this is the table the page could show instead.
    print("\nper drawing, named / shown:")
    table = {}
    for n in names:
        group = [r for r in rows if r["drawing"] == n]
        hits = sum(r["correct"] for r in group)
        table[n] = {"named": hits, "shown": len(group),
                    "distance": round(float(np.mean([r["distance"] for r in group])), 3),
                    "excursion": round(float(np.mean([r["excursion"] for r in group])), 3)}
        print(f"  {n:18s} {hits:2d}/{len(group):2d}  d={table[n]['distance']:.3f} "
              f"exc={table[n]['excursion']:.3f}")

    OUT.write_text(json.dumps({"models": out, "winner": winner,
                               "per_drawing": table, "answers": len(rows),
                               "sessions": len(sessions),
                               "excursion_recomputed": filled,
                               "excursion_agreement": agreement},
                              ensure_ascii=False, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
