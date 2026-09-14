"""
Does the detour depend on the size of the shape, or on how much choice of
placement the search had?

BACKLOG #11. DETOUR_RATIO = 1.25 +-15% was calibrated on 1-3 km shapes. Three
large fits have since come in at 1.82, 1.93 and 2.18, and the service now
quotes a rider 42.5-57.5 km for a route that turns out to be 72.2. POC 23
rejected barriers, grid orientation and outline reversals as the cause and was
left with one candidate mechanism: a small shape is picked from thousands of
viable placements and a large one from a couple of dozen, so 1.25 is a
best-of-thousands figure and 2.0 is nearly take-what-you-get.

That is testable, because the choice is a knob we own. The pipeline fits
N_CANDIDATES placements and keeps the one with the lowest shape distance, so
"how much choice" IS N_CANDIDATES. Fit M placements at a fixed size, then read
off what the best-of-k would have been for every k up to M.

Averaged over random permutations of the M fits rather than over the coarse
scan's own order, because POC 17 established that the coarse score does not
predict fidelity - taking its first k would measure the scan's ranking and not
the effect of choice.

Two sizes, so the two explanations separate:

  - if the curves for small and large shapes lie on top of each other, choice
    explains everything and size explains nothing;
  - if the large curve sits above the small one at every k, size costs
    something of its own and the constant has to depend on it.

Run:  python poc24_placement_choice.py
Out:  poc24_placement_choice.png, poc24_placement_choice.json
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

import route_feasibility as rf
from heart_route_poc2 import NoRouteFoundError
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M, SEARCH_LAT,
                              SEARCH_LON, build_center_grid, build_street_index,
                              place_shape, select_candidates)
from poc6_shapes import coarse_scan, refine
from poc15_wiggle import wander
from region_graph import region_graph
from shape_library import resample_by_arclength

SHAPE = "heart"
MODE = "bike"
# The two ends of the product's range. 10 km is where DETOUR_RATIO was
# calibrated and lands inside its predicted range; 50 km is where the service
# promised 42.5-57.5 and delivered 72.2.
TARGETS_KM = (10.0, 50.0)
M_FITS = 20              # placements actually fitted per size
DRAWS = 2000             # permutations averaged over
PLACEMENT_SLACK = 1.0
OUT_PNG = Path(__file__).with_name("poc24_placement_choice.png")
OUT_JSON = Path(__file__).with_name("poc24_placement_choice.json")


def best_of_k(values: np.ndarray, keys: np.ndarray, rng) -> np.ndarray:
    """
    Expected `values` of the item the pipeline would keep, for every k.

    The pipeline ranks by shape distance (`keys`) and keeps the winner, so the
    detour it ends up with is the detour OF the lowest-distance fit among k -
    not the lowest detour among k. Averaging the wrong one of those two would
    turn the question into "does more choice find shorter routes", which nobody
    asked.
    """
    m = len(values)
    out = np.zeros(m)
    for k in range(1, m + 1):
        acc = 0.0
        for _ in range(DRAWS):
            idx = rng.choice(m, size=k, replace=False)
            acc += values[idx[np.argmin(keys[idx])]]
        out[k - 1] = acc / DRAWS
    return out


def run_size(target_km: float, cfg: dict) -> dict:
    p = rf.plan(SHAPE, target_km, MODE)
    width_m, points = float(p.width_m), int(p.points)
    dense = resample_by_arclength(SHAPE, 4000)
    closed = np.vstack([dense, dense[:1]])
    perimeter = float(np.hypot(*np.diff(closed, axis=0).T).sum())
    template_km = perimeter * width_m / 1000.0
    half = max(4500.0, width_m * PLACEMENT_SLACK)
    print(f"\n=== {target_km:.0f} km target: {width_m / 1000:.1f} km wide, "
          f"{points} points, outline {template_km:.1f} km, network +-{half:.0f} m",
          flush=True)

    graph = region_graph(SEARCH_LAT, SEARCH_LON, half, mode=MODE)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)

    margin = max(400.0, half - width_m * 0.75)
    centers, _, _ = build_center_grid(region, margin, GRID_STEP_M)
    scored = coarse_scan(tree, centers, SHAPE, width_m, (0.0,))
    viable = int(np.isfinite(scored["score"]).sum())
    print(f"  {len(centers)} placements, {viable} viable", flush=True)

    rows = select_candidates(scored, M_FITS, MIN_SEPARATION_M)
    fits = []
    for i, row in enumerate(rows):
        centre = np.array([row["x"], row["y"]])
        t0 = time.time()
        try:
            f = refine(graph, SHAPE, centre, row["rotation"], width_m, points=points)
        except NoRouteFoundError:
            f = None
        if f is None:
            print(f"  [{i + 1}/{len(rows)}] no route", flush=True)
            continue
        km = f["metrics"]["route_km"]
        fits.append({"distance": float(f["distance"]),
                     "detour": km / template_km,
                     "route_km": km,
                     "wander": float(wander(f["route_xy"],
                                            place_shape(closed, centre, width_m, 0.0)))})
        print(f"  [{i + 1}/{len(rows)}] distance {f['distance']:.3f}, "
              f"detour {fits[-1]['detour']:.2f}, {km:.1f} km "
              f"({time.time() - t0:.0f}s)", flush=True)

    if not fits:
        return {"status": "no fits", "target_km": target_km}
    det = np.array([f["detour"] for f in fits])
    dist = np.array([f["distance"] for f in fits])
    rng = np.random.default_rng(0)
    return {"status": "ok", "target_km": target_km, "width_m": width_m,
            "points": points, "template_km": template_km,
            "viable": viable, "n_fits": len(fits),
            "detour_all": det.tolist(), "distance_all": dist.tolist(),
            "detour_by_k": best_of_k(det, dist, rng).tolist(),
            "distance_by_k": best_of_k(dist, dist, rng).tolist()}


def main() -> None:
    cfg = rf.MODES[MODE]
    out = {f"{t:.0f}km": run_size(t, cfg) for t in TARGETS_KM}
    OUT_JSON.write_text(json.dumps(out, indent=2))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.4))
    colors = {"10km": "#2f5d50", "50km": "#b4622c"}
    for name, r in out.items():
        if r.get("status") != "ok":
            continue
        k = np.arange(1, len(r["detour_by_k"]) + 1)
        ax1.plot(k, r["detour_by_k"], lw=2, color=colors[name],
                 label=f"{name} target ({r['width_m'] / 1000:.1f} km wide, "
                       f"{r['viable']} viable)")
        ax2.plot(k, r["distance_by_k"], lw=2, color=colors[name], label=name)
    ax1.axhline(rf.DETOUR_RATIO, ls="--", lw=1, color="#888")
    ax1.annotate(f"DETOUR_RATIO = {rf.DETOUR_RATIO}", (1, rf.DETOUR_RATIO),
                 xytext=(2, rf.DETOUR_RATIO + 0.04), fontsize=8, color="#666")
    ax1.set_xlabel("placements the search could choose from (N_CANDIDATES)")
    ax1.set_ylabel("detour of the route it kept")
    ax1.set_title("Does choice buy a shorter route?", fontsize=11)
    ax2.set_xlabel("placements the search could choose from")
    ax2.set_ylabel("shape distance of the route it kept")
    ax2.set_title("Does choice buy a better shape?", fontsize=11)
    for ax in (ax1, ax2):
        ax.legend(fontsize=8, frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")
    for name, r in out.items():
        if r.get("status") == "ok":
            d = r["detour_by_k"]
            print(f"  {name}: detour best-of-1 {d[0]:.2f} -> "
                  f"best-of-{len(d)} {d[-1]:.2f}")


if __name__ == "__main__":
    main()
