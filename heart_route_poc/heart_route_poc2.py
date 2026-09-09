"""
POC 2 - Shape-aware route matching
==================================

POC 1 showed the basic idea works: an ideal heart snapped onto Taipei's walking
network is recognisably a heart. It also showed exactly where it breaks. Each
contour point was snapped to its own nearest junction, independently of every
other point, so the algorithm could not make the one trade that matters:

    a junction 60 m off the contour but on a through street is usually a far
    better target than one 20 m off that needs a 300 m detour to reach.

POC 2 makes that trade. Three changes over POC 1:

  1. Resample the contour by ARC LENGTH, so samples spread evenly instead of
     bunching at the cusps (uniform `t` clusters points where the curve turns).
  2. Keep the k nearest junctions per contour point as CANDIDATES rather than
     committing to the nearest one.
  3. Choose one candidate per point with a VITERBI dynamic program that scores
     snap error and routing detour together, over the whole closed loop.

This is map-matching applied to a synthetic target shape instead of a GPS
trace. Everything else - the network download, the projection, the parametric
heart - is reused unchanged from POC 1.

Run:  python heart_route_poc2.py
Out:  heart_route_poc2.png, poc1_vs_poc2.png
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
from scipy.spatial import cKDTree

# POC 1 stays the baseline and the shared toolbox; nothing there is duplicated.
from heart_route_poc import (
    CENTER_LAT,
    CENTER_LON,
    HEART_WIDTH_M,
    build_route,
    download_walk_graph,
    generate_heart_points,
    snap_points_to_graph,
    transform_shape_to_map,
)

N_POINTS = 40
N_CANDIDATES = 10          # k nearest junctions kept per contour point
SNAP_WEIGHT = 1.0          # metres of snap error worth one metre of detour
DEVIATION_WEIGHT = 10.0    # weight on how far a path strays from the ideal curve
CANDIDATE_RADIUS_M = 260.0 # ignore junctions further than this from the contour
OUT_PNG = Path(__file__).with_name("heart_route_poc2.png")
COMPARE_PNG = Path(__file__).with_name("poc1_vs_poc2.png")


# ---------------------------------------------------------------------------
# Improvement 1 - even spacing along the contour
# ---------------------------------------------------------------------------
def resample_by_arclength(n_points: int = N_POINTS, oversample: int = 4000) -> np.ndarray:
    """
    Sample the heart curve at equal ARC LENGTH rather than at equal `t`.

    The parametric heart moves fastest along the flanks and slowest at the
    cusps, so uniform `t` (what POC 1 used) piles points into the cleft and the
    bottom tip and leaves the long flanks thinly covered. That is backwards:
    the flanks are easy for a street grid to follow, the cusps are hard, and
    crowding samples into the hard places buys nothing.

    The curve is densely sampled, its cumulative arc length is computed, and
    `n_points` positions are interpolated at equal spacing along it.
    """
    dense = generate_heart_points(oversample)
    closed = np.vstack([dense, dense[:1]])  # close the loop before measuring

    seg = np.hypot(*np.diff(closed, axis=0).T)
    cumulative = np.concatenate([[0.0], np.cumsum(seg)])
    total = cumulative[-1]

    targets = np.linspace(0.0, total, n_points, endpoint=False)
    x = np.interp(targets, cumulative, closed[:, 0])
    y = np.interp(targets, cumulative, closed[:, 1])
    return np.column_stack([x, y])


# ---------------------------------------------------------------------------
# Improvement 2 - candidate sets instead of a single nearest node
# ---------------------------------------------------------------------------
def build_candidate_sets(
    graph_proj: nx.MultiDiGraph,
    points_proj: np.ndarray,
    k: int = N_CANDIDATES,
    radius_m: float = CANDIDATE_RADIUS_M,
    min_degree: int = 3,
) -> tuple[list[list[int]], list[dict[int, float]]]:
    """
    For each contour point keep the k nearest junctions as candidates.

    Dead ends (degree 1) stay excluded for the reason POC 1 established: they
    can only be left the way they were entered. Beyond that this commits to
    nothing - the dynamic program picks from the whole set.

    Candidates further than `radius_m` are dropped so the DP cannot wander off
    the shape, but the nearest candidate is always kept even if it is further,
    so no contour point is ever left without options.

    Returns the candidate node ids per point, and the snap distance (the
    "emission cost") of each candidate.
    """
    junctions = [n for n, deg in graph_proj.to_undirected().degree() if deg >= min_degree]
    node_xy = np.array([[graph_proj.nodes[n]["x"], graph_proj.nodes[n]["y"]] for n in junctions])
    tree = cKDTree(node_xy)

    k = min(k, len(junctions))
    dists, idxs = tree.query(points_proj, k=k)
    if k == 1:
        dists, idxs = dists[:, None], idxs[:, None]

    candidates: list[list[int]] = []
    emissions: list[dict[int, float]] = []
    for row_d, row_i in zip(dists, idxs):
        keep = [(float(d), junctions[i]) for d, i in zip(row_d, row_i) if d <= radius_m]
        if not keep:  # nothing within the radius - fall back to the single nearest
            keep = [(float(row_d[0]), junctions[row_i[0]])]
        candidates.append([n for _, n in keep])
        emissions.append({n: d for d, n in keep})
    return candidates, emissions


# ---------------------------------------------------------------------------
# Improvement 3 - transition costs and the Viterbi pass
# ---------------------------------------------------------------------------
def compute_transition_costs(
    graph_proj: nx.MultiDiGraph,
    candidates: list[list[int]],
    points_proj: np.ndarray,
    reference_tree: cKDTree | None = None,
    deviation_weight: float = DEVIATION_WEIGHT,
) -> list[dict[tuple[int, int], float]]:
    """
    Cost of walking from each candidate of point i to each candidate of i+1.

    Two terms, both in metres so they can simply be added:

      excess detour  = max(0, path_length - ideal_gap)
          How much longer the street path is than the straight line the ideal
          contour would have taken. Measuring excess rather than raw length
          keeps the score comparable across segments and charges nothing when
          the streets happen to line up.

      shape deviation = mean distance from the path to the ideal curve
          Length alone is blind to WHERE a path goes, so a cost built only from
          length rewards cutting the corner off a curve - the shortcut is
          shorter, and nothing charges for leaving the shape. This term prices
          that in, and it is what makes the DP shape-aware rather than merely
          efficient.

    One Dijkstra per source candidate, bounded by a cutoff, serves every target
    at that step. The cutoff grows if a step is unreachable within it (rare, but
    a river or a rail corridor can do it).
    """
    n = len(candidates)
    transitions: list[dict[tuple[int, int], float]] = []

    for i in range(n):
        j = (i + 1) % n  # wraps at the end: the loop must close
        ideal_gap = float(np.hypot(*(points_proj[j] - points_proj[i])))
        targets = set(candidates[j])
        step: dict[tuple[int, int], float] = {}

        cutoff = max(400.0, 4.0 * ideal_gap)
        for _attempt in range(3):
            step.clear()
            for u in candidates[i]:
                lengths, paths = nx.single_source_dijkstra(
                    graph_proj, u, cutoff=cutoff, weight="length"
                )
                for v in targets:
                    if v not in lengths:
                        continue
                    cost = max(0.0, lengths[v] - ideal_gap)
                    if reference_tree is not None and deviation_weight:
                        cost += deviation_weight * _path_deviation(
                            graph_proj, paths[v], reference_tree
                        )
                    step[(u, v)] = cost
            if step:
                break
            cutoff *= 3.0  # nothing reachable; widen and retry

        transitions.append(step)
    return transitions


def _path_deviation(
    graph_proj: nx.MultiDiGraph, path: list[int], reference_tree: cKDTree
) -> float:
    """Mean distance, in metres, from a candidate path to the ideal curve."""
    if len(path) < 2:
        node = graph_proj.nodes[path[0]]
        return float(reference_tree.query([[node["x"], node["y"]]])[0][0])
    samples = _densify(route_to_xy(graph_proj, path), spacing=20.0)
    return float(reference_tree.query(samples)[0].mean())


def viterbi_closed_loop(
    candidates: list[list[int]],
    emissions: list[dict[int, float]],
    transitions: list[dict[tuple[int, int], float]],
    snap_weight: float = SNAP_WEIGHT,
) -> tuple[list[int], float]:
    """
    Pick one candidate per contour point, minimising total cost around the loop.

        total = snap_weight * sum(snap error) + sum(excess detour)

    A plain Viterbi pass handles an open chain, but this route is a cycle: the
    last point must join back to the first, and that choice depends on where the
    chain started. The fix is to pin the first point to each of its candidates
    in turn, run a full DP for each, and keep the cheapest complete loop. With
    k candidates that is k passes - cheap enough to be exact rather than clever.

    Returns the chosen node per contour point and the total cost.
    """
    n = len(candidates)
    best_assignment: list[int] | None = None
    best_cost = float("inf")

    for start in candidates[0]:
        # dp[node] = cost of the best partial path ending at `node` at step i.
        dp: dict[int, float] = {start: snap_weight * emissions[0][start]}
        back: list[dict[int, int]] = [{} for _ in range(n)]

        for i in range(n - 1):
            step = transitions[i]
            nxt: dict[int, float] = {}
            for v in candidates[i + 1]:
                cheapest, arg = float("inf"), None
                for u, cost_u in dp.items():
                    edge = step.get((u, v))
                    if edge is None:
                        continue
                    total = cost_u + edge
                    if total < cheapest:
                        cheapest, arg = total, u
                if arg is not None:
                    nxt[v] = cheapest + snap_weight * emissions[i + 1][v]
                    back[i + 1][v] = arg
            dp = nxt
            if not dp:
                break  # this start cannot reach the next point at all

        if not dp:
            continue

        # Close the loop: the final point must connect back to `start`.
        closing = transitions[n - 1]
        cheapest, arg = float("inf"), None
        for u, cost_u in dp.items():
            edge = closing.get((u, start))
            if edge is None:
                continue
            total = cost_u + edge
            if total < cheapest:
                cheapest, arg = total, u
        if arg is None or cheapest >= best_cost:
            continue

        # Walk the back-pointers to recover the assignment.
        assignment = [0] * n
        assignment[n - 1] = arg
        for i in range(n - 1, 0, -1):
            assignment[i - 1] = back[i][assignment[i]]
        best_assignment, best_cost = assignment, cheapest

    if best_assignment is None:
        msg = "no closed loop found through any candidate assignment"
        raise RuntimeError(msg)
    return best_assignment, best_cost


# ---------------------------------------------------------------------------
# Measuring the result
# ---------------------------------------------------------------------------
def route_to_xy(graph_proj: nx.MultiDiGraph, route: list[int]) -> np.ndarray:
    """
    Trace the route as a polyline in metres, following real edge geometry.

    osmnx's simplification collapses a chain of nodes into one edge and keeps
    the true shape in the edge's `geometry`. Joining node coordinates with
    straight lines (as POC 1's plot did) would cut every curve, which flatters
    the result and distorts the shape metrics below.
    """
    pieces: list[np.ndarray] = []
    for u, v in zip(route[:-1], route[1:]):
        data = min(graph_proj[u][v].values(), key=lambda d: d["length"])
        geom = data.get("geometry")
        if geom is not None:
            pts = np.asarray(geom.coords)
            # Edge geometry is stored in one direction; flip it if we traverse
            # the edge the other way.
            start = np.array([graph_proj.nodes[u]["x"], graph_proj.nodes[u]["y"]])
            if np.hypot(*(pts[0] - start)) > np.hypot(*(pts[-1] - start)):
                pts = pts[::-1]
        else:
            pts = np.array([
                [graph_proj.nodes[u]["x"], graph_proj.nodes[u]["y"]],
                [graph_proj.nodes[v]["x"], graph_proj.nodes[v]["y"]],
            ])
        pieces.append(pts if not pieces else pts[1:])
    return np.vstack(pieces)


def _densify(polyline: np.ndarray, spacing: float = 5.0) -> np.ndarray:
    """Resample a polyline at roughly `spacing` metres, for fair point comparison."""
    seg = np.hypot(*np.diff(polyline, axis=0).T)
    cumulative = np.concatenate([[0.0], np.cumsum(seg)])
    total = cumulative[-1]
    if total == 0:
        return polyline
    targets = np.arange(0.0, total, spacing)
    return np.column_stack([
        np.interp(targets, cumulative, polyline[:, 0]),
        np.interp(targets, cumulative, polyline[:, 1]),
    ])


def shape_similarity(route_xy: np.ndarray, reference_xy: np.ndarray) -> dict[str, float]:
    """
    How closely does the route trace the ideal heart? Two directions, both in
    metres, because they fail in different ways:

    `reference_xy` is a densely sampled ideal curve, NOT the handful of contour
    points fed to the router. Scoring each variant against its own sample
    polygon would compare them to different targets - uniform-`t` sampling and
    arc-length sampling approximate the curve differently - so both variants are
    measured against the same dense reference.

      * `coverage`  - from each ideal point to the nearest route point. High
                      means part of the heart was never walked (a missing lobe).
      * `stray`     - from each route point to the nearest ideal point. High
                      means the route wandered somewhere the heart never went
                      (a detour spur).

    A route can score well on one and badly on the other, so both are reported
    along with their mean (a symmetric Chamfer distance) and the 95th
    percentile of the worse direction.
    """
    ideal_dense = _densify(reference_xy)
    route_dense = _densify(route_xy)

    to_route = cKDTree(route_dense).query(ideal_dense)[0]
    to_ideal = cKDTree(ideal_dense).query(route_dense)[0]

    return {
        "coverage_mean_m": float(to_route.mean()),
        "coverage_p95_m": float(np.percentile(to_route, 95)),
        "stray_mean_m": float(to_ideal.mean()),
        "stray_p95_m": float(np.percentile(to_ideal, 95)),
        "chamfer_m": float((to_route.mean() + to_ideal.mean()) / 2.0),
    }


def evaluate(
    graph_proj: nx.MultiDiGraph,
    reference_xy: np.ndarray,
    snapped: list[int],
) -> dict:
    """Run the routing step for an assignment and collect every metric."""
    from collections import Counter

    route, total_m, failures = build_route(graph_proj, snapped)
    route_xy = route_to_xy(graph_proj, route)

    perimeter_m = float(np.hypot(*np.diff(reference_xy, axis=0).T).sum())

    seen = Counter(frozenset((u, v)) for u, v in zip(route[:-1], route[1:]))
    backtracked = sum(count - 1 for count in seen.values() if count > 1)

    metrics = {
        "route_km": total_m / 1000.0,
        "ideal_km": perimeter_m / 1000.0,
        "detour_ratio": total_m / perimeter_m,
        "backtracked_edges": backtracked,
        "route_edges": max(len(route) - 1, 0),
        "unique_nodes": len(set(snapped)),
        "failed_segments": len(failures),
    }
    metrics.update(shape_similarity(route_xy, reference_xy))
    return {"route": route, "route_xy": route_xy, "snapped": snapped, "metrics": metrics}


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def _draw(ax, graph_proj, heart_proj, result, title, route_color):
    """Draw one panel: network, ideal contour, chosen nodes, actual route."""
    ox.plot_graph(
        graph_proj, ax=ax, node_size=0, edge_color="#dddddd", edge_linewidth=0.4,
        bgcolor="white", show=False, close=False,
    )
    ideal_closed = np.vstack([heart_proj, heart_proj[:1]])
    ax.plot(ideal_closed[:, 0], ideal_closed[:, 1], color="#e8443a",
            linewidth=2.0, linestyle="--", label="Ideal heart contour", zorder=3)

    route_xy = result["route_xy"]
    ax.plot(route_xy[:, 0], route_xy[:, 1], color=route_color, linewidth=2.6,
            alpha=0.9, label="Actual walking route", zorder=4)

    snap_xy = np.array([[graph_proj.nodes[n]["x"], graph_proj.nodes[n]["y"]]
                        for n in result["snapped"]])
    ax.scatter(snap_xy[:, 0], snap_xy[:, 1], s=22, color="#f6a800",
               edgecolor="black", linewidth=0.4, label="Chosen road nodes", zorder=5)

    margin = 350.0
    ax.set_xlim(heart_proj[:, 0].min() - margin, heart_proj[:, 0].max() + margin)
    ax.set_ylim(heart_proj[:, 1].min() - margin, heart_proj[:, 1].max() + margin)
    m = result["metrics"]
    ax.set_title(f"{title}\n{m['route_km']:.2f} km  ·  detour {m['detour_ratio']:.2f}x  ·  "
                 f"chamfer {m['chamfer_m']:.0f} m  ·  {m['backtracked_edges']} backtracked edges",
                 fontsize=11, color="black")
    ax.legend(loc="upper right", fontsize=8, facecolor="white", framealpha=0.9)


def plot_result(graph_proj, heart_proj, result, out_path=OUT_PNG):
    fig, ax = plt.subplots(figsize=(11, 11))
    _draw(ax, graph_proj, heart_proj, result, "POC 2 - candidate sets + Viterbi DP", "#1a7f37")
    fig.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {out_path}")


def plot_comparison(graph_proj, heart_poc1, result1, heart_poc2, result2, out_path=COMPARE_PNG):
    fig, axes = plt.subplots(1, 2, figsize=(20, 10.5))
    _draw(axes[0], graph_proj, heart_poc1, result1, "POC 1 - greedy nearest-node snap", "#1f6fb4")
    _draw(axes[1], graph_proj, heart_poc2, result2, "POC 2 - candidate sets + Viterbi DP", "#1a7f37")
    fig.suptitle("Heart route on Taipei walking streets - POC 1 vs POC 2", fontsize=15)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {out_path}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def dense_reference(lat, lon, width_m, crs, n=4000) -> np.ndarray:
    """The ideal heart as a closed, densely sampled polyline - the yardstick both
    variants are scored against."""
    dense = generate_heart_points(n)
    closed = np.vstack([dense, dense[:1]])
    return transform_shape_to_map(closed, lat, lon, width_m, crs)


def run_poc2(graph_proj, heart_proj, reference_xy, k, snap_weight, radius_m,
             deviation_weight=DEVIATION_WEIGHT):
    """Candidate sets -> transition costs -> Viterbi -> route."""
    candidates, emissions = build_candidate_sets(
        graph_proj, heart_proj, k=k, radius_m=radius_m
    )
    sizes = [len(c) for c in candidates]
    print(f"  candidates per point: min {min(sizes)}, mean {np.mean(sizes):.1f}, max {max(sizes)}")

    t0 = time.perf_counter()
    reference_tree = cKDTree(_densify(reference_xy, spacing=5.0))
    transitions = compute_transition_costs(
        graph_proj, candidates, heart_proj, reference_tree, deviation_weight
    )
    print(f"  transition costs: {sum(len(t) for t in transitions)} pairs "
          f"in {time.perf_counter() - t0:.1f}s")

    assignment, cost = viterbi_closed_loop(candidates, emissions, transitions, snap_weight)
    print(f"  viterbi total cost: {cost:.0f}")
    return evaluate(graph_proj, reference_xy, assignment)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=int, default=N_POINTS)
    parser.add_argument("--candidates", type=int, default=N_CANDIDATES,
                        help="k nearest junctions kept per contour point")
    parser.add_argument("--snap-weight", type=float, default=SNAP_WEIGHT,
                        help="weight on snap error relative to detour, in metres per metre")
    parser.add_argument("--radius-m", type=float, default=CANDIDATE_RADIUS_M)
    parser.add_argument("--deviation-weight", type=float, default=DEVIATION_WEIGHT,
                        help="weight on how far a candidate path strays from the ideal curve")
    parser.add_argument("--width-m", type=float, default=HEART_WIDTH_M)
    parser.add_argument("--lat", type=float, default=CENTER_LAT)
    parser.add_argument("--lon", type=float, default=CENTER_LON)
    args = parser.parse_args()

    print("Downloading / loading walking network")
    graph_proj = download_walk_graph(args.lat, args.lon)
    crs = graph_proj.graph["crs"]

    # POC 1 baseline: uniform-t sampling, greedy nearest-junction snapping.
    print("\nPOC 1 baseline (greedy nearest-node snap)")
    heart_poc1 = transform_shape_to_map(
        generate_heart_points(args.points), args.lat, args.lon, args.width_m, crs
    )
    reference = dense_reference(args.lat, args.lon, args.width_m, crs)
    snapped_poc1, _ = snap_points_to_graph(graph_proj, heart_poc1)
    result1 = evaluate(graph_proj, reference, snapped_poc1)

    # POC 2: arc-length resampling, candidate sets, Viterbi over the closed loop.
    print("\nPOC 2 (arc-length resampling + candidate sets + Viterbi DP)")
    heart_poc2 = transform_shape_to_map(
        resample_by_arclength(args.points), args.lat, args.lon, args.width_m, crs
    )
    result2 = run_poc2(graph_proj, heart_poc2, reference, args.candidates,
                       args.snap_weight, args.radius_m, args.deviation_weight)

    print("\nPlotting")
    plot_result(graph_proj, heart_poc2, result2)
    plot_comparison(graph_proj, heart_poc1, result1, heart_poc2, result2)

    rows = [
        ("route distance (km)", "route_km", "{:.2f}"),
        ("detour ratio vs ideal", "detour_ratio", "{:.2f}x"),
        ("backtracked edges", "backtracked_edges", "{:.0f}"),
        ("shape chamfer (m)", "chamfer_m", "{:.1f}"),
        ("coverage mean / p95 (m)", None, None),
        ("stray mean / p95 (m)", None, None),
        ("unique nodes used", "unique_nodes", "{:.0f}"),
        ("failed segments", "failed_segments", "{:.0f}"),
    ]
    m1, m2 = result1["metrics"], result2["metrics"]
    print(f"\n{'metric':<26}{'POC 1':>16}{'POC 2':>16}")
    print("-" * 58)
    for label, key, fmt in rows:
        if key is None:
            which = "coverage" if label.startswith("coverage") else "stray"
            a = f"{m1[which + '_mean_m']:.0f} / {m1[which + '_p95_m']:.0f}"
            b = f"{m2[which + '_mean_m']:.0f} / {m2[which + '_p95_m']:.0f}"
        else:
            a, b = fmt.format(m1[key]), fmt.format(m2[key])
        print(f"{label:<26}{a:>16}{b:>16}")


if __name__ == "__main__":
    main()
