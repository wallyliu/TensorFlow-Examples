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
        # The floor is derived from the OUTLINE, so it fingerprints which
        # drawing a round showed. See `current_drawing_only`.
        floors = {r["shape"]: r.get("floor_km")
                  for r in json.loads(
                      (RESULTS / f"poc{n}_stimuli.json").read_text())}
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
                    "floor_km": floors.get(item.get("drawing", item["shape"])),
                    "correct": bool(a["correct"]),
                    "blank": a["chosen"] == "__none__",
                    "xy": item["xy"],
                })
    return rows


def current_drawing_only(rows: list) -> tuple[list, dict]:
    """Drop answers about a version of a shape that no longer exists.

    THE POOL IS KEYED BY NAME AND FIVE SHAPES WERE REDRAWN under theirs. The
    gear got its centre bore between round 33 and round 37 - the rider asked
    for it - so "gear" in the pool is two different pictures, and pooling them
    reports the current one as 4 named out of 13 when three of three raters
    named it in round four. Same for the house (a door), the cup (a thicker
    handle), the butterfly and the leaf.

    `min_distance_km` is computed from the outline, so it fingerprints the
    drawing: an answer counts only if the shape's floor then equals its floor
    now. Everything is Taipei at the same street scale, so the floors are
    comparable across rounds.
    """
    import routeshape.feasibility as rf
    import routeshape.street_scale as ss

    scale = ss.scale_for(25.04, 121.54, "bike", rf.MODES["bike"]["street_scale_m"])
    now: dict = {}
    for r in rows:
        name = r["drawing"]
        if name not in now:
            try:
                now[name] = round(rf.min_distance_km(name, "bike", scale), 1)
            except Exception:                        # noqa: BLE001
                now[name] = None
    keep, dropped = [], {}
    for r in rows:
        floor, current = r["floor_km"], now[r["drawing"]]
        if floor is None or current is None or abs(floor - current) < 0.05:
            keep.append(r)
        else:
            dropped.setdefault(r["drawing"], set()).add((floor, current))
    return keep, dropped


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


RIDGE = 1.0


def predict(beta, X, floor):
    return floor + (1 - floor) / (1 + np.exp(-np.clip(X @ beta, -40, 40)))


def logistic_fit(y: np.ndarray, X: np.ndarray, floor: np.ndarray,
                 ridge: float = RIDGE):
    """Penalised logistic regression with a per-row chance floor.

    The floor matters: a rater picking blind from fifteen options is right 7% of
    the time, and a model that can drive the predicted rate to zero will spend
    its parameters fitting that impossible region.

    THE PENALTY IS NOT OPTIONAL HERE. Half the drawings were named by everyone
    or by nobody, so a per-drawing model separates the data perfectly and its
    coefficients run off to infinity - the first cut of this returned betas in
    the thousands and an AIC that looked decisive because of it. A likelihood
    that can be driven to zero makes every comparison built on it meaningless.
    A small ridge keeps every model estimable and comparable.
    """
    def objective(beta):
        p = np.clip(predict(beta, X, floor), 1e-9, 1 - 1e-9)
        ll = float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))
        return -ll + ridge * float(np.dot(beta, beta))

    best = None
    for seed in (0.0, 1.0, -1.0):
        res = minimize(objective, np.full(X.shape[1], seed), method="L-BFGS-B")
        if best is None or res.fun < best.fun:
            best = res
    p = np.clip(predict(best.x, X, floor), 1e-9, 1 - 1e-9)
    ll = float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))
    return best.x, ll


def cross_validated(y, X, floor, folds: int = 5, seed: int = 0) -> float:
    """Mean held-out log-loss per answer.

    AIC counts parameters; this asks the question the product actually has -
    given the answers so far, how well is the NEXT answer predicted. With
    sixty-one drawings and 259 answers those are not the same question, and
    only the second one is worth shipping on.
    """
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(y))
    loss, n = 0.0, 0
    for f in range(folds):
        test = order[f::folds]
        train = np.setdiff1d(order, test)
        beta, _ = logistic_fit(y[train], X[train], floor[train])
        p = np.clip(predict(beta, X[test], floor[test]), 1e-9, 1 - 1e-9)
        loss += -float(np.sum(y[test] * np.log(p)
                              + (1 - y[test]) * np.log(1 - p)))
        n += len(test)
    return loss / n


def main() -> None:
    install_everything()
    rows = load()
    if not rows:
        print("no answers found")
        return
    rows, dropped = current_drawing_only(rows)
    if dropped:
        print("answers dropped - the shape has been redrawn since:")
        for name, pairs in sorted(dropped.items()):
            was = ", ".join(f"{a} km" for a, _ in sorted(pairs))
            print(f"  {name:16s} was {was}, now {sorted(pairs)[0][1]} km")
        print()
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
    print(f"{'model':20s} {'params':>6s} {'logL':>9s} {'AIC':>9s} "
          f"{'cv logloss':>11s}")
    fits = {}
    for name, X in models.items():
        beta, ll = logistic_fit(y, X, floor)
        fits[name] = {"logL": ll, "aic": 2 * X.shape[1] - 2 * ll,
                      "params": X.shape[1], "cv": cross_validated(y, X, floor),
                      "beta": [round(float(b), 4) for b in beta]}
    for name, f in fits.items():
        print(f"{name:20s} {f['params']:6d} {f['logL']:9.2f} {f['aic']:9.2f} "
              f"{f['cv']:11.4f}")
        out[name] = f
    winner = min(fits, key=lambda k: fits[k]["cv"])
    print(f"\nbest by held-out log-loss: {winner}")

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
                          "cv": cross_validated(y[keep], X, floor[keep]),
                          "beta": [round(float(b), 4) for b in beta]}
    for name, f in sub_fits.items():
        print(f"  {name:20s} {f['params']:4d} {f['logL']:9.2f} {f['aic']:9.2f} "
              f"{f['cv']:11.4f}")
    out["well_sampled"] = sub_fits
    out["well_sampled_drawings"] = kept_names

    slope = fits["drawing+excursion"]["beta"][-1]
    print(f"\nexcursion slope within a drawing: {slope:.1f} log-odds per 1.0,"
          f" so +0.01 multiplies the odds of being named by "
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
