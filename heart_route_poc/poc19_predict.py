"""
Can anything cheap predict how the fit will turn out?

Two findings arrive at the same place. POC 17: the coarse scan's rank and the
final shape distance correlate at -0.024, so stage 1 tells you which placements
are routable and nothing else, and the only workaround was to fit more of them
at 23 s a request. POC 18: two raters, seventeen of seventeen, prefer a shape
with a feature amputated over one that wobbles everywhere, and no weighting of
wander against shape distance reproduces their answers.

Forty fitted candidates across five shapes, each scored beforehand with cheap
features and afterwards with both outcomes. Three answers, and the useful one
was not the question asked.

1. NOTHING CHEAP PREDICTS SHAPE FIDELITY. The best of six features is p95
   distance-to-network at rho = -0.287 (p = 0.07), and its sign says placements
   FURTHER from the network score better, which is not a mechanism, it is noise.
   POC 17's finding stands and cannot be fixed with these features.

2. CHEAP FEATURES DO PREDICT WANDER: worst gap rho = +0.355 (p = 0.025), spread
   of gaps +0.325 (p = 0.041). Sensible - a contour that strays far from the
   network forces the route to go the long way round - and it means stage 1 can
   screen for wander even though it cannot screen for fidelity.

3. THE ONE THAT MATTERS: among fitted routes, wander and shape distance are
   independent (rho = +0.104, p = 0.52). They are separate axes. You cannot get
   a low-wander route by minimising shape distance, which is exactly why wander
   has to be a constraint rather than a term - and why the raters could see
   something the metric was blind to.

Also worth recording: `frac_within_s` came out constant at 1.00 for every
candidate and has no correlation to report, because MAX_GAP_M (250 m) is already
stricter than the bike street scale (280 m). The admissibility filter had been
guaranteeing the feature all along.

The constraint sweep that follows from this lives in server/app.py: 0.30 cuts
mean wander from 0.263 to 0.240 for +0.001 of shape distance; 0.25 costs +0.013
and pushes a shape back over the 0.10 a person can see.

Run:  python poc19_predict.py
Out:  poc19_predict.png, poc19_predict.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer
from scipy.stats import spearmanr

import route_feasibility as rf
from heart_route_poc import download_walk_graph
from heart_route_poc2 import NoRouteFoundError
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M,
                              SEARCH_LAT, SEARCH_LON, build_center_grid,
                              build_street_index, place_shape, select_candidates)
from poc6_shapes import CONTOUR_SAMPLES, ROTATIONS_DEG, coarse_scan, refine
from poc15_wiggle import wander
from shape_library import SHAPES, resample_by_arclength

MODE = "bike"
N_SHORTLIST = 8
TARGETS = {"heart": 10.0, "crescent": 9.0, "triangle": 8.0,
           "star5": 14.0, "trex": 34.0}
OUT_PNG = Path(__file__).with_name("poc19_predict.png")
OUT_JSON = Path(__file__).with_name("poc19_predict.json")

FEATURES = ["mean_m", "p95_m", "max_m", "std_m", "frac_within_s", "frac_within_half_s"]


def contour_features(tree, contour_xy: np.ndarray, street_scale_m: float) -> dict:
    """
    What the placement looks like before anything is routed.

    `frac_within_s` is the one the other findings point at: not how far the
    contour sits from the network on average, but how much of it has a street
    close enough to follow. A placement can have a fine mean and still force the
    route to wander wherever it does not.
    """
    d = tree.query(contour_xy)[0]
    return {"mean_m": float(d.mean()), "p95_m": float(np.percentile(d, 95)),
            "max_m": float(d.max()), "std_m": float(d.std()),
            "frac_within_s": float((d <= street_scale_m).mean()),
            "frac_within_half_s": float((d <= street_scale_m / 2).mean())}


def main() -> None:
    cfg = rf.MODES[MODE]
    scale = cfg["street_scale_m"]
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M, mode=MODE)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    rows = []
    for shape in SHAPES:
        plan = rf.plan(shape, TARGETS[shape], MODE)
        if not plan.feasible:
            continue
        width_m, points = plan.width_m, plan.points
        print(f"\n=== {shape}: {width_m:.0f} m wide, {points} points", flush=True)

        margin = max(400.0, NETWORK_HALF_SIZE_M - width_m * 0.75)
        centers, _, _ = build_center_grid(region, margin, GRID_STEP_M)
        scored = coarse_scan(tree, centers, shape, width_m, ROTATIONS_DEG)
        if not np.isfinite(scored["score"]).any():
            continue

        dense = resample_by_arclength(shape, 4000)
        contour = resample_by_arclength(shape, CONTOUR_SAMPLES)
        for rank, row in enumerate(select_candidates(scored, N_SHORTLIST,
                                                     MIN_SEPARATION_M)):
            centre = np.array([row["x"], row["y"]])
            placed = place_shape(contour, centre, width_m, row["rotation"])
            feats = contour_features(tree, placed, scale)
            t0 = time.time()
            try:
                fit = refine(graph, shape, centre, row["rotation"], width_m,
                             points=points)
            except NoRouteFoundError:
                fit = None
            if fit is None:
                continue
            template = place_shape(np.vstack([dense, dense[:1]]), centre, width_m, 0.0)
            rows.append({"shape": shape, "coarse_rank": rank,
                         "coarse_score": float(row["score"]), **feats,
                         "shape_distance": fit["distance"],
                         "wander": wander(fit["route_xy"], template),
                         "route_km": fit["metrics"]["route_km"],
                         "fit_seconds": round(time.time() - t0, 1)})
            print(f"  rank {rank}: frac_within_s {feats['frac_within_s']:.2f}  "
                  f"-> distance {fit['distance']:.3f}, wander {rows[-1]['wander']:.3f}",
                  flush=True)
            OUT_JSON.write_text(json.dumps(rows, indent=2))

    print(f"\n{len(rows)} fitted candidates\n")
    print(f"  {'feature':<20}{'rho vs distance':>17}{'p':>8}"
          f"{'rho vs wander':>16}{'p':>8}")
    stats = {}
    for f in FEATURES + ["coarse_score", "coarse_rank"]:
        x = [r[f] for r in rows]
        rd, pd_ = spearmanr(x, [r["shape_distance"] for r in rows])
        rw, pw = spearmanr(x, [r["wander"] for r in rows])
        stats[f] = {"rho_distance": rd, "p_distance": pd_,
                    "rho_wander": rw, "p_wander": pw}
        print(f"  {f:<20}{rd:>17.3f}{pd_:>8.3f}{rw:>16.3f}{pw:>8.3f}")

    rd, pd_ = spearmanr([r["wander"] for r in rows],
                        [r["shape_distance"] for r in rows])
    print(f"\n  wander vs shape distance among fitted routes: "
          f"rho {rd:+.3f} (p={pd_:.3f})")
    stats["wander_vs_distance"] = {"rho": rd, "p": pd_}

    OUT_JSON.write_text(json.dumps({"rows": rows, "stats": stats}, indent=2))

    best = max(FEATURES, key=lambda f: abs(stats[f]["rho_distance"]))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4))
    colours = {s: c for s, c in zip(SHAPES,
                                    ["#2f5d50", "#b4622c", "#7b4a8a", "#2b6cb0", "#8a8f8a"])}
    for ax, (xf, yf, xl, yl) in zip(
            (ax1, ax2),
            [("coarse_score", "shape_distance", "coarse score (stage 1 today)",
              "final shape distance"),
             (best, "shape_distance", f"{best} (stage 1 proposed)",
              "final shape distance")]):
        for s in SHAPES:
            sub = [r for r in rows if r["shape"] == s]
            if sub:
                ax.scatter([r[xf] for r in sub], [r[yf] for r in sub],
                           s=46, color=colours[s], label=s, alpha=0.85)
        ax.set_xlabel(xl, fontsize=9)
        ax.set_ylabel(yl, fontsize=9)
        ax.grid(alpha=0.25, lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    ax1.set_title(f"rho = {stats['coarse_score']['rho_distance']:+.3f}", fontsize=10)
    ax2.set_title(f"rho = {stats[best]['rho_distance']:+.3f}", fontsize=10)
    ax1.legend(frameon=False, fontsize=8)
    fig.suptitle("What a cheap score can know about an expensive fit", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
