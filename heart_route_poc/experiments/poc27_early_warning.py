"""
Can the service tell you it will not work BEFORE it spends a minute finding out?

The worst thing left in the product: pick Keelung, wait a minute, get told the
street network cannot draw a heart. The answer is true and a minute late.

The obvious predictor failed. Last turn I proposed the city's directional
street scale, on a +0.74 correlation with shape distance over seven cities.
Fitted with width and tested leave-one-out over thirteen routes it classifies
into good/marginal/poor at 62%, against 54% for saying "good" every time - and
it puts Keelung, the one case it exists to catch, in the wrong band. The
correlation was one point: drop Keelung and +0.74 becomes +0.47.

This tests a different one. The coarse scan already counts how many placements
of the shape fit anywhere in the network, and the service runs it anyway before
the expensive part. Over fourteen routes spanning three shapes, four sizes and
seven cities, log(viable placements) against the shape distance that came out
is r = -0.85, and the two worst results - Taipei 101 at 27 viable, Keelung at
99 - are the two lowest.

Two things have to be established before that can be used:

1. The RATE, not the count. Runs scanned different numbers of candidate
   centres, so a raw count confounds "few fit" with "few tried".
2. Leave-one-out band accuracy, the standard that killed the first predictor.
   A correlation is not a classifier.

And one thing has to be worth it: the coarse scan has to be a small fraction of
the total, or an early warning saves nothing. That is timed here too.

RESULT. As a three-way grader it fails the same way the street scale did:
leave-one-out band accuracy 62% against 44% for saying "good" every time. Fit a
line to log(rate) and bin it and you get good/marginal confusions everywhere.

But that is not the question the product asks. The question is "will this come
out unusable", and on that it separates completely:

    viable rate of the five POOR routes   5.2%  9.7%  19.3%  22.0%  39.1%
    viable rate of the other eleven      69.6% ... 99.7%

Nothing in between. Any threshold from 40% to 69% catches 5 of 5 bad routes
with 0 false alarms out of 11, with a 30-point margin either side, so the
service uses the midpoint. Sixteen routes over three shapes, four sizes and
seven cities.

The timing works: network 21.1s, coarse scan 0.1s, fitting 21.5s. The scan is
free and the warning lands at half the wait. It cannot move any earlier without
the network, which is why /api/plan stays instant and map-free and the check
lives in /api/route.

Run:  python poc27_early_warning.py
Out:  poc27_early_warning.png, poc27_early_warning.json
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

import routeshape.feasibility as rf
import routeshape.street_scale as ss
from routeshape.matching import NoRouteFoundError
from routeshape.placement import (GRID_STEP_M, MIN_SEPARATION_M, build_center_grid,
                              build_street_index, select_candidates)
from routeshape.search import coarse_scan, refine
from routeshape.region.graph import RegionNotCovered, region_graph
from routeshape.shapes.library import resample_by_arclength

# Three shapes, four distances, seven cities - chosen so size and place vary
# independently rather than together.
CASES = [
    ("heart", 10.0, "台北", 25.0400, 121.5400),
    ("heart", 20.0, "台北", 25.0400, 121.5400),
    ("heart", 35.0, "台北", 25.0400, 121.5400),
    ("heart", 50.0, "台北", 25.0400, 121.5400),
    ("star5", 20.0, "台北", 25.0400, 121.5400),
    ("star5", 35.0, "台北", 25.0400, 121.5400),
    ("triangle", 10.0, "台北", 25.0400, 121.5400),
    ("heart", 10.0, "板橋", 25.0143, 121.4672),
    ("heart", 10.0, "桃園", 24.9937, 121.3010),
    ("heart", 10.0, "新竹", 24.8039, 120.9715),
    ("heart", 10.0, "宜蘭", 24.7570, 121.7530),
    ("heart", 10.0, "基隆", 25.1283, 121.7419),
    ("heart", 20.0, "基隆", 25.1283, 121.7419),
    ("heart", 10.0, "台中", 24.1477, 120.6736),
    ("heart", 20.0, "台中", 24.1477, 120.6736),
    ("triangle", 10.0, "基隆", 25.1283, 121.7419),
]
MODE = "bike"
FITS = 3
PLACEMENT_SLACK = 1.0
BANDS = ((0.10, "good"), (0.18, "marginal"), (9e9, "poor"))
OUT_PNG = Path(__file__).with_name("poc27_early_warning.png")
OUT_JSON = Path(__file__).with_name("poc27_early_warning.json")

_nets: dict = {}


def net_for(lat, lon, half):
    key = (round(lat, 4), round(lon, 4), round(half))
    if key not in _nets:
        g = region_graph(lat, lon, half, mode=MODE)
        to_proj = Transformer.from_crs("EPSG:4326", g.graph["crs"], always_xy=True)
        _nets.clear()
        _nets[key] = {"graph": g, "tree": build_street_index(g),
                      "region": np.array(to_proj.transform(lon, lat))}
    return _nets[key]


def band(distance: float) -> str:
    for limit, name in BANDS:
        if distance < limit:
            return name
    return BANDS[-1][1]


def run_case(shape, target_km, city, lat, lon) -> dict:
    scale = ss.scale_for(lat, lon, MODE, rf.MODES[MODE]["street_scale_m"])
    p = rf.plan(shape, target_km, MODE, scale)
    if not p.feasible:
        return {"status": "infeasible", "reason": p.reason}
    width_m, points = float(p.width_m), int(p.points)
    dense = resample_by_arclength(shape, 4000)
    closed = np.vstack([dense, dense[:1]])
    per = float(np.hypot(*np.diff(closed, axis=0).T).sum())
    template_km = per * width_m / 1000.0
    half = max(4500.0, width_m * PLACEMENT_SLACK)

    t_net = time.time()
    try:
        net = net_for(lat, lon, half)
    except RegionNotCovered as exc:
        return {"status": "not covered", "reason": str(exc)}
    t_net = time.time() - t_net

    t_scan = time.time()
    centers, _, _ = build_center_grid(net["region"],
                                      max(400.0, half - width_m * 0.75), GRID_STEP_M)
    scored = coarse_scan(net["tree"], centers, shape, width_m, (0.0,))
    viable = int(np.isfinite(scored["score"]).sum())
    t_scan = time.time() - t_scan
    if viable == 0:
        return {"status": "no placement", "centers": len(centers), "viable": 0,
                "scan_seconds": round(t_scan, 1), "net_seconds": round(t_net, 1)}

    t_fit = time.time()
    got = []
    for row in select_candidates(scored, FITS, MIN_SEPARATION_M):
        try:
            f = refine(net["graph"], shape, np.array([row["x"], row["y"]]),
                       row["rotation"], width_m, points=points)
        except NoRouteFoundError:
            f = None
        if f is not None:
            got.append({"distance": float(f["distance"]),
                        "detour": f["metrics"]["route_km"] / template_km})
    t_fit = time.time() - t_fit
    if not got:
        return {"status": "no route", "centers": len(centers), "viable": viable}
    kept = min(got, key=lambda g: g["distance"])
    return {"status": "ok", "shape": shape, "target_km": target_km, "city": city,
            "width_m": width_m, "points": points, "street_scale_m": scale,
            "centers": len(centers), "viable": viable,
            "viable_rate": viable / len(centers),
            "kept_distance": kept["distance"], "kept_detour": kept["detour"],
            "band": band(kept["distance"]),
            "net_seconds": round(t_net, 1), "scan_seconds": round(t_scan, 1),
            "fit_seconds": round(t_fit, 1)}


def leave_one_out(x, y) -> tuple[float, list]:
    """Band accuracy when each point is predicted by a fit that excludes it."""
    x, y = np.asarray(x), np.asarray(y)
    preds = []
    for i in range(len(y)):
        m = np.ones(len(y), bool)
        m[i] = False
        A = np.column_stack([np.ones(m.sum()), x[m]])
        b, *_ = np.linalg.lstsq(A, y[m], rcond=None)
        preds.append(float(b[0] + b[1] * x[i]))
    hits = sum(band(p) == band(t) for p, t in zip(preds, y))
    return hits / len(y), preds


def main() -> None:
    out = {}
    for shape, km, city, lat, lon in CASES:
        key = f"{shape}@{km:.0f}/{city}"
        print(f"\n=== {key} ===", flush=True)
        out[key] = run_case(shape, km, city, lat, lon)
        r = out[key]
        if r.get("status") == "ok":
            print(f"  {r['viable']}/{r['centers']} viable ({r['viable_rate']:.1%}), "
                  f"distance {r['kept_distance']:.3f} [{r['band']}], "
                  f"net {r['net_seconds']}s scan {r['scan_seconds']}s "
                  f"fit {r['fit_seconds']}s", flush=True)
        else:
            print(f"  {r.get('status')}: {r.get('reason', '')}", flush=True)
        OUT_JSON.write_text(json.dumps(out, indent=2))

    ok = {k: v for k, v in out.items() if v.get("status") == "ok"}
    if len(ok) < 4:
        print("\ntoo few cases to judge")
        return
    lr = np.log(np.array([v["viable_rate"] for v in ok.values()]))
    y = np.array([v["kept_distance"] for v in ok.values()])
    acc, preds = leave_one_out(lr, y)
    always_good = sum(1 for v in y if band(v) == "good") / len(y)
    print(f"\nlog(viable rate) vs distance: r = {np.corrcoef(lr, y)[0, 1]:+.2f}")
    print(f"leave-one-out band accuracy: {acc:.0%}   "
          f"(saying 'good' every time: {always_good:.0%})")
    print(f"\n{'case':22s}{'viable':>9}{'actual':>9}{'LOO':>8}  band")
    for (k, v), p in zip(ok.items(), preds):
        mark = "" if band(p) == v["band"] else "  MISS"
        print(f"{k:22s}{v['viable_rate']:>8.1%}{v['kept_distance']:>9.3f}"
              f"{p:>8.3f}  {v['band']:<9}{band(p):<9}{mark}")
    scan = np.mean([v["scan_seconds"] for v in ok.values()])
    fit = np.mean([v["fit_seconds"] for v in ok.values()])
    net = np.mean([v["net_seconds"] for v in ok.values()])
    print(f"\nmean seconds: network {net:.1f}, coarse scan {scan:.1f}, fitting {fit:.1f}")
    print(f"a warning after the scan arrives {fit / (net + scan + fit):.0%} sooner")
    out["_summary"] = {"r": float(np.corrcoef(lr, y)[0, 1]), "loo_accuracy": acc,
                       "always_good": always_good, "n": len(y),
                       "mean_net_s": net, "mean_scan_s": scan, "mean_fit_s": fit}
    OUT_JSON.write_text(json.dumps(out, indent=2))

    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    colors = {"good": "#2f5d50", "marginal": "#b4622c", "poor": "#9a3b1f"}
    for k, v in ok.items():
        ax.scatter(v["viable_rate"] * 100, v["kept_distance"], s=46,
                   color=colors[v["band"]])
    ax.set_xscale("log")
    ax.axhline(0.10, ls="--", lw=1, color="#888")
    ax.axhline(0.18, ls="--", lw=1, color="#888")
    ax.set_xlabel("placements that fit (% of those tried, log scale)")
    ax.set_ylabel("shape distance that came out")
    ax.set_title(f"Does the coarse scan know in advance?  "
                 f"r = {np.corrcoef(lr, y)[0, 1]:+.2f}, "
                 f"leave-one-out {acc:.0%}", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT_PNG, dpi=140)
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
