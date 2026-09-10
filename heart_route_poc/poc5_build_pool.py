"""
POC 5, step 1 - build the pool of routes to be judged by a human.

POC 4's honest limit was that its battery encoded MY assumptions about which
deformations should cost more. This step assembles the material for the first
real ground truth in the project: a set of route shapes a person can rank.

Two rules govern how these are rendered, and both matter more than they look:

  * No ideal contour is drawn. With a dashed target on the page the judgement
    silently becomes "does it hug that line", which is what chamfer already
    measures. Without it, the question is the one the product actually cares
    about: does this look like a heart.
  * No street background. Otherwise familiarity with an area, or the density of
    the local grid, leaks into a judgement that is supposed to be about shape.

The pool mixes real Taipei routes with two deformations applied TO A REAL ROUTE
rather than to a smooth template - so the cleft question POC 4 left open is
asked with the same jagged street texture as everything else, and cannot be
answered by "one of them is obviously synthetic".

Run:  python poc5_build_pool.py
Out:  poc5_pool.npz
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from pyproj import Transformer

from heart_route_poc import download_walk_graph, generate_heart_points
from heart_route_poc3 import (
    GRID_STEP_M, HEART_WIDTH_M, MIN_SEPARATION_M, NETWORK_HALF_SIZE_M,
    ROTATIONS_DEG, SEARCH_LAT, SEARCH_LON, build_center_grid, build_street_index,
    coarse_scan, refine_placement, select_candidates,
)
from shape_metrics import (
    chamfer_placed, chamfer_upright, procrustes_upright_fft, resample_closed,
    turning_upright,
)

N_PLACEMENTS = 12
DISPLAY_N = 400          # points kept per route for the labelling page
OUT_NPZ = Path(__file__).with_name("poc5_pool.npz")

PITFALL_TILTED = (25.0382, 121.5400, 30.0)


def _nearest_index(points: np.ndarray, target: np.ndarray) -> int:
    return int(np.argmin(np.hypot(*(points - target).T)))


def deform_real_route(route_xy: np.ndarray, reference_xy: np.ndarray, n: int = 512):
    """
    Apply POC 4's two competing deformations to a REAL route.

    `fill_cleft` flattens the notch between the lobes; the control transplants
    the identical per-point displacement magnitudes to an equally long arc on
    the flank. POC 4 asserted the first should be judged worse and all four
    metrics disagreed - this is what puts that to a person.
    """
    route = resample_closed(route_xy, n)

    # Locate the cleft and the two lobe peaks on the route, via the ideal
    # contour whose geometry we know: its index 0 is the cleft.
    ideal = resample_closed(reference_xy, n)
    cleft_xy = ideal[0]
    upper = ideal[ideal[:, 1] > ideal[:, 1].mean()]
    left_peak_xy = upper[np.argmax(upper[:, 1] - 0.001 * upper[:, 0])]
    right_peak_xy = upper[np.argmax(upper[:, 1] + 0.001 * upper[:, 0])]

    cleft = _nearest_index(route, cleft_xy)
    left = _nearest_index(route, left_peak_xy)
    right = _nearest_index(route, right_peak_xy)

    # Walk from one peak to the other through the cleft.
    forward = [(left + i) % n for i in range((right - left) % n + 1)]
    if cleft not in forward:
        forward = [(right + i) % n for i in range((left - right) % n + 1)]
    indices = forward

    start, end = route[indices[0]], route[indices[-1]]
    ts = np.linspace(0.0, 1.0, len(indices))[:, None]
    filled = route.copy()
    filled[indices] = start * (1 - ts) + end * ts
    magnitudes = np.linalg.norm(filled[indices] - route[indices], axis=1)

    # Control: same magnitudes, different place, along the local normal.
    # Normals are taken from a SMOOTHED copy of the route. A street route turns
    # 90 degrees every block, so its raw local normals swing wildly, and pushing
    # neighbouring points along them makes the displaced arc cross itself. That
    # self-intersection reads as "broken" rather than "deformed", which would
    # bias the very judgement this control exists to make fair.
    window = 15
    kernel = np.ones(window) / window
    smoothed = np.column_stack([
        np.convolve(np.r_[route[-window:, axis], route[:, axis], route[:window, axis]],
                    kernel, mode="same")[window:-window]
        for axis in (0, 1)
    ])
    tangent = np.gradient(smoothed, axis=0)
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    # Centre the control a quarter turn from the cleft: that lands mid-flank,
    # clear of BOTH defining features. An earlier version offset by half a turn
    # and landed on the bottom tip - which destroys the heart's other cusp, so
    # it tested "which cusp matters more" rather than "does the cleft matter".
    centre = (cleft + n // 4) % n
    offset = (centre - len(indices) // 2) % n
    control_idx = [(offset + i) % n for i in range(len(indices))]
    control = route.copy()
    control[control_idx] = route[control_idx] + normal[control_idx] * magnitudes[:, None]

    return filled, control, float(magnitudes.mean())


def main() -> None:
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    crs = graph.graph["crs"]
    to_proj = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    upright_template = generate_heart_points(2048) * HEART_WIDTH_M

    region = np.array(to_proj.transform(SEARCH_LON, SEARCH_LAT))
    tree = build_street_index(graph)
    centers, _, _ = build_center_grid(
        region, NETWORK_HALF_SIZE_M - HEART_WIDTH_M * 0.75, GRID_STEP_M
    )
    scored = coarse_scan(tree, centers, HEART_WIDTH_M, rotations=ROTATIONS_DEG)
    shortlist = select_candidates(scored, N_PLACEMENTS, MIN_SEPARATION_M)

    items: list[dict] = []
    best_real = None
    for rank, row in enumerate(shortlist, start=1):
        result = refine_placement(graph, np.array([row["x"], row["y"]]),
                                  row["rotation"], HEART_WIDTH_M)
        if result is None:
            continue
        items.append({"id": f"real{rank:02d}", "kind": "real",
                      "xy": result["route_xy"], "reference": result["reference"]})
        if best_real is None or result["metrics"]["backtracked_edges"] < best_real[1]:
            best_real = (len(items) - 1, result["metrics"]["backtracked_edges"])

    lat, lon, rot = PITFALL_TILTED
    tilted = refine_placement(graph, np.array(to_proj.transform(lon, lat)), rot, HEART_WIDTH_M)
    items.append({"id": "tilted30", "kind": "tilted",
                  "xy": tilted["route_xy"], "reference": tilted["reference"]})

    source = items[best_real[0]]
    filled, control, shift = deform_real_route(source["xy"], source["reference"])
    print(f"  cleft/flank deformations built from {source['id']}, "
          f"mean displacement {shift:.0f} m")
    items.append({"id": "cleft_filled", "kind": "deformed", "xy": filled,
                  "reference": source["reference"]})
    items.append({"id": "flank_changed", "kind": "deformed", "xy": control,
                  "reference": source["reference"]})

    # Score every item with all four metrics.
    print(f"\n{'id':<16}{'kind':<10}{'chamfer_placed':>16}{'chamfer↑':>12}"
          f"{'procrustes↑':>14}{'turning↑':>11}")
    payload = {}
    for item in items:
        scores = {
            "chamfer_placed": chamfer_placed(item["xy"], item["reference"]),
            "chamfer_upright": chamfer_upright(item["xy"], upright_template),
            "procrustes_upright": procrustes_upright_fft(item["xy"], upright_template),
            "turning_upright": turning_upright(item["xy"], upright_template),
        }
        item["scores"] = scores
        print(f"{item['id']:<16}{item['kind']:<10}{scores['chamfer_placed']:>16.1f}"
              f"{scores['chamfer_upright']:>12.3f}{scores['procrustes_upright']:>14.3f}"
              f"{scores['turning_upright']:>11.3f}")
        display = resample_closed(item["xy"], DISPLAY_N)
        payload[f"{item['id']}__xy"] = display
        payload[f"{item['id']}__scores"] = np.array(
            [scores[k] for k in ("chamfer_placed", "chamfer_upright",
                                 "procrustes_upright", "turning_upright")])
        payload[f"{item['id']}__kind"] = np.array(item["kind"])

    np.savez_compressed(OUT_NPZ, ids=np.array([i["id"] for i in items]), **payload)
    print(f"\nsaved {OUT_NPZ} ({len(items)} items)")


if __name__ == "__main__":
    main()
