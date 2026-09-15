"""
Is one street_scale enough for the whole island?

BACKLOG #5. MODES carries a single street_scale_m - 280 m for cycling - and it
was fitted in Taipei. POC 22 then measured the median distance from a random
point to the nearest rideable street and found a six-fold spread across cities:
Taipei 14 m, Zhongli 25 m, Luodong 31 m, Keelung 84 m. That looks damning, but
it is not the same quantity, so it cannot simply be substituted - inventing a
transfer like that is exactly how a made-up "vs Taipei" baseline got into POC
22's first draft.

Two measurements here, and the second is the one that decides it.

1. The DIRECTIONAL street scale: the median distance to the nearest street
   heading within +-10 degrees of a chosen direction, averaged over twelve
   directions. That is much closer to what street_scale means - how far apart
   the streets that can carry an intended heading are - and in Taipei it comes
   out near 180 m against a 14 m distance-to-any-street. This is a property of
   the network and costs no fitting.

2. Whether it PREDICTS anything. The same shape at the same target distance is
   fitted in each city, and the detour and shape distance recorded. A constant
   that is wrong for a city should show up as that city's routes coming out
   long or unrecognisable.

If the fitted results track the directional scale, street_scale becomes a
per-place lookup. If they do not, the single constant stays and BACKLOG #5 is
closed as measured-and-refuted rather than left open on the strength of a
statistic that turned out not to matter.

Run:  python poc26_city_scale.py
Out:  poc26_city_scale.png, poc26_city_scale.json
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
from scipy.spatial import cKDTree

import routeshape.feasibility as rf
from routeshape.matching import NoRouteFoundError
from routeshape.placement import (GRID_STEP_M, MIN_SEPARATION_M,
                              build_center_grid, build_street_index,
                              place_shape, select_candidates)
from routeshape.search import coarse_scan, refine
from routeshape.region.graph import RegionNotCovered, region_graph
from routeshape.shapes.library import resample_by_arclength

CITIES = [
    ("台北", 25.0400, 121.5400), ("板橋", 25.0143, 121.4672),
    ("桃園", 24.9937, 121.3010), ("新竹", 24.8039, 120.9715),
    ("宜蘭", 24.7570, 121.7530), ("基隆", 25.1283, 121.7419),
    ("台中", 24.1477, 120.6736),
]
SHAPE = "heart"
TARGET_KM = 10.0
MODE = "bike"
HALF_M = 5000.0
FITS = 3
STEP_M = 15.0
DIR_TOLERANCE_DEG = 10.0
OUT_PNG = Path(__file__).with_name("poc26_city_scale.png")
OUT_JSON = Path(__file__).with_name("poc26_city_scale.json")


def directional_scale(graph, rng) -> dict:
    """Median distance to the nearest street heading a chosen way, over 12 ways."""
    X = {n: (d["x"], d["y"]) for n, d in graph.nodes(data=True)}
    pts, brg = [], []
    for u, v, _ in graph.edges(data=True):
        (x1, y1), (x2, y2) = X[u], X[v]
        L = float(np.hypot(x2 - x1, y2 - y1))
        if L <= 0:
            continue
        k = max(2, int(L / STEP_M) + 1)
        t = np.linspace(0, 1, k)
        pts.append(np.column_stack([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t]))
        brg.append(np.full(k, np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180.0))
    P = np.vstack(pts)
    B = np.concatenate(brg)
    base = cKDTree(P)
    lo, hi = P.min(axis=0), P.max(axis=0)
    S = rng.uniform(lo, hi, size=(3000, 2))
    # Only sample where there is a town at all. Without this the answer is
    # dominated by the sea and the mountains, which no route will ever cross.
    S = S[base.query(S)[0] <= 250.0]
    if len(S) < 200:
        return {"directional_m": None, "any_m": None, "samples": int(len(S))}
    per = []
    for th in range(0, 180, 15):
        sel = np.abs((B - th + 90) % 180 - 90) <= DIR_TOLERANCE_DEG
        if sel.sum() < 100:
            continue
        per.append(float(np.median(cKDTree(P[sel]).query(S)[0])))
    return {"directional_m": float(np.mean(per)) if per else None,
            "any_m": float(np.median(base.query(S)[0])),
            "samples": int(len(S))}


def fit_city(graph, lat, lon) -> dict:
    p = rf.plan(SHAPE, TARGET_KM, MODE)
    width_m, points = float(p.width_m), int(p.points)
    dense = resample_by_arclength(SHAPE, 4000)
    closed = np.vstack([dense, dense[:1]])
    per = float(np.hypot(*np.diff(closed, axis=0).T).sum())
    template_km = per * width_m / 1000.0

    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(lon, lat))
    tree = build_street_index(graph)
    centers, _, _ = build_center_grid(region, max(400.0, HALF_M - width_m * 0.75),
                                      GRID_STEP_M)
    scored = coarse_scan(tree, centers, SHAPE, width_m, (0.0,))
    viable = int(np.isfinite(scored["score"]).sum())
    if viable == 0:
        return {"fit": "no placement", "viable": 0}
    got = []
    for row in select_candidates(scored, FITS, MIN_SEPARATION_M):
        try:
            f = refine(graph, SHAPE, np.array([row["x"], row["y"]]),
                       row["rotation"], width_m, points=points)
        except NoRouteFoundError:
            f = None
        if f is None:
            continue
        got.append({"distance": float(f["distance"]),
                    "detour": f["metrics"]["route_km"] / template_km,
                    "route_km": f["metrics"]["route_km"]})
    if not got:
        return {"fit": "no route", "viable": viable}
    kept = min(got, key=lambda g: g["distance"])
    return {"fit": "ok", "viable": viable, "n_fits": len(got),
            "kept_distance": kept["distance"], "kept_detour": kept["detour"],
            "kept_km": kept["route_km"], "template_km": template_km,
            "width_m": width_m, "points": points}


def main() -> None:
    rng = np.random.default_rng(0)
    out = {}
    for name, lat, lon in CITIES:
        print(f"\n=== {name} ===", flush=True)
        t0 = time.time()
        try:
            graph = region_graph(lat, lon, HALF_M, mode=MODE)
        except RegionNotCovered as exc:
            print(f"  not covered: {exc}", flush=True)
            out[name] = {"status": "not covered"}
            continue
        rec = {"status": "ok", "lat": lat, "lon": lon,
               "nodes": graph.number_of_nodes()}
        rec.update(directional_scale(graph, rng))
        print(f"  directional {rec['directional_m']:.0f} m, "
              f"any-street {rec['any_m']:.0f} m", flush=True)
        rec.update(fit_city(graph, lat, lon))
        if rec.get("fit") == "ok":
            print(f"  kept distance {rec['kept_distance']:.3f}, "
                  f"detour {rec['kept_detour']:.2f}, "
                  f"{rec['kept_km']:.1f} km ({time.time() - t0:.0f}s)", flush=True)
        out[name] = rec
        OUT_JSON.write_text(json.dumps(out, indent=2))

    ok = {k: v for k, v in out.items()
          if v.get("status") == "ok" and v.get("fit") == "ok"}
    if len(ok) >= 3:
        x = np.array([v["directional_m"] for v in ok.values()])
        for key, label in (("kept_distance", "shape distance"),
                           ("kept_detour", "detour")):
            y = np.array([v[key] for v in ok.values()])
            r = float(np.corrcoef(x, y)[0, 1])
            print(f"\ndirectional scale vs {label}: r = {r:+.2f} (n={len(x)})")
            out.setdefault("_correlations", {})[label] = r
    OUT_JSON.write_text(json.dumps(out, indent=2))

    if ok:
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2))
        names = list(ok)
        x = [ok[n]["directional_m"] for n in names]
        for ax, key, lab in ((a1, "kept_distance", "shape distance of the kept route"),
                             (a2, "kept_detour", "detour of the kept route")):
            ax.scatter(x, [ok[n][key] for n in names], s=42, color="#2f5d50")
            for n in names:
                ax.annotate(n, (ok[n]["directional_m"], ok[n][key]),
                            textcoords="offset points", xytext=(6, 3), fontsize=8)
            ax.set_xlabel("directional street scale (m)")
            ax.set_ylabel(lab)
            ax.spines[["top", "right"]].set_visible(False)
        a1.axhline(0.10, ls="--", lw=1, color="#888")
        fig.suptitle(f"Does a city's street spacing predict its routes? "
                     f"({SHAPE}, {TARGET_KM:.0f} km)", fontsize=11)
        fig.tight_layout(); fig.savefig(OUT_PNG, dpi=140)
    print(f"\nwrote {OUT_JSON.name}")


if __name__ == "__main__":
    main()
