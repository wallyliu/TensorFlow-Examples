"""
POC 3 - Automatic location search
=================================

POC 1 asked whether a heart-shaped route was possible at all. POC 2 improved
the algorithm that fits one to the streets. Both used the same hand-picked
centre in Da'an District, chosen because it was convenient.

POC 2 ended with a measurement that motivates this POC: better routing bought
4 m of shape accuracy, and the remaining error is dominated by whether the
local street grid happens to suit the shape at all. No cleverness in the
matcher fixes a cusp that has no street near it. So the question here is:

    Given a city, WHERE should the heart go - and at what orientation?

Two stages, because the search space is far too large to run POC 2 on every
candidate:

  Stage 1 (coarse, ~seconds for thousands of placements)
      Score a placement by how close the ideal contour lies to ANY walkable
      street, using one k-d tree built over the whole network. This ignores
      connectivity entirely - it only asks "is there pavement along this
      curve?" - which is exactly the cheap question worth asking first.

  Stage 2 (exact, ~seconds each for a handful)
      Run the full POC 2 pipeline on the best few placements and rank them by
      the real shape metric. This is where connectivity, detour and
      backtracking finally get priced in.

The heart's size stays fixed at 2 km so results stay comparable with POC 1 and
POC 2; only the centre and the rotation are searched.

Run:  python heart_route_poc3.py
Out:  poc3_search_map.png, poc3_best_route.png, poc3_top_routes.png
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
from pyproj import Transformer
from scipy.spatial import cKDTree

from heart_route_poc import CENTER_LAT, CENTER_LON, download_walk_graph, generate_heart_points
from heart_route_poc2 import (
    DEVIATION_WEIGHT,
    NoRouteFoundError,
    N_CANDIDATES,
    SNAP_WEIGHT,
    _densify,
    evaluate,
    resample_by_arclength,
    run_poc2,
)

# Search region: a 9 km x 9 km box around central Taipei.
SEARCH_LAT = 25.040
SEARCH_LON = 121.540
NETWORK_HALF_SIZE_M = 4500.0

HEART_WIDTH_M = 2000.0     # fixed, so POC 1 / 2 / 3 stay comparable
GRID_STEP_M = 200.0        # spacing of candidate centres
# Upright only, by default. Searching +-30 deg was measured to buy exactly
# nothing (chamfer 17.9 m either way) while making the result read far less like
# a heart - the shape metric is computed against the ROTATED reference, so it is
# blind to tilt by construction. Pass --rotations to explore anyway.
ROTATIONS_DEG = (0,)
CONTOUR_SAMPLES = 180      # dense contour points used for coarse scoring
STREET_SPACING_M = 15.0    # resolution of the street point cloud
MAX_GAP_M = 250.0          # reject a placement if any part of the contour is this far from a street
N_REFINE = 20              # placements passed to stage 2 (each costs ~5 s; see README)
MIN_SEPARATION_M = 700.0   # keep the refined candidates from being near-duplicates
CHAMFER_TOLERANCE_M = 1.5  # placements this close in chamfer count as equally good

OUT_SEARCH = Path(__file__).with_name("poc3_search_map.png")
OUT_BEST = Path(__file__).with_name("poc3_best_route.png")
OUT_TOP = Path(__file__).with_name("poc3_top_routes.png")


# ---------------------------------------------------------------------------
# Placing a shape without going through lat/lon
# ---------------------------------------------------------------------------
def place_shape(
    shape: np.ndarray, center_xy: np.ndarray, width_m: float, rotation_deg: float = 0.0
) -> np.ndarray:
    """
    Rotate, scale and translate a normalised shape directly in projected metres.

    POC 1's `transform_shape_to_map` took a lat/lon centre, which is the wrong
    interface here: the search generates thousands of centres already in the
    projected CRS, and round-tripping each through WGS84 would be both slower
    and lossier. Rotation happens before scaling, so `width_m` always describes
    the heart's own width along its own axis, whatever the tilt.
    """
    theta = np.radians(rotation_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    rotation = np.array([[cos_t, -sin_t], [sin_t, cos_t]])
    return (shape @ rotation.T) * width_m + np.asarray(center_xy)


# ---------------------------------------------------------------------------
# Stage 1 - coarse scoring over a grid of placements
# ---------------------------------------------------------------------------
def build_street_index(graph_proj: nx.MultiDiGraph, spacing: float = STREET_SPACING_M) -> cKDTree:
    """
    A k-d tree over points sampled every `spacing` metres along every edge.

    Sampling edges rather than indexing nodes matters: junctions in Taipei sit
    100-200 m apart, so a node-only index would report a contour running
    perfectly along the middle of a long block as being 80 m from a street.
    """
    points: list[np.ndarray] = []
    for u, v, data in graph_proj.edges(data=True):
        geom = data.get("geometry")
        if geom is not None:
            line = np.asarray(geom.coords)
        else:
            line = np.array([
                [graph_proj.nodes[u]["x"], graph_proj.nodes[u]["y"]],
                [graph_proj.nodes[v]["x"], graph_proj.nodes[v]["y"]],
            ])
        points.append(_densify(line, spacing) if len(line) > 1 else line)
    cloud = np.vstack(points)
    print(f"  street index: {len(cloud):,} points every {spacing:.0f} m")
    return cKDTree(cloud)


def coarse_scan(
    street_tree: cKDTree,
    centers: np.ndarray,
    width_m: float = HEART_WIDTH_M,
    rotations: tuple[int, ...] = ROTATIONS_DEG,
    contour_samples: int = CONTOUR_SAMPLES,
    max_gap_m: float = MAX_GAP_M,
) -> np.ndarray:
    """
    Score every (centre, rotation) pair by how closely streets follow the contour.

        score = mean distance to nearest street + 0.5 * 95th percentile

    The percentile term is what separates a placement that is uniformly 30 m
    off - fine, the matcher absorbs that - from one that is perfect for
    three quarters of the loop and 200 m off along a riverbank. The mean alone
    rates those alike; the shape does not.

    Placements where any part of the contour is further than `max_gap_m` from
    a street are rejected outright: some stretch has no pavement at all, and no
    routing can invent it.

    Returns a structured array with one row per (centre, rotation).
    """
    shape = resample_by_arclength(contour_samples)
    rows = []

    for rotation in rotations:
        # The contour is the same for every centre at a given rotation, so
        # build it once and broadcast it across all centres in one query.
        offsets = place_shape(shape, np.zeros(2), width_m, rotation)
        query = (centers[:, None, :] + offsets[None, :, :]).reshape(-1, 2)
        dists = street_tree.query(query)[0].reshape(len(centers), contour_samples)

        mean = dists.mean(axis=1)
        p95 = np.percentile(dists, 95, axis=1)
        worst = dists.max(axis=1)
        score = np.where(worst > max_gap_m, np.inf, mean + 0.5 * p95)

        for i, center in enumerate(centers):
            rows.append((center[0], center[1], rotation, score[i], mean[i], p95[i], worst[i]))

    return np.array(
        rows,
        dtype=[("x", float), ("y", float), ("rotation", float),
               ("score", float), ("mean", float), ("p95", float), ("worst", float)],
    )


def select_candidates(
    scored: np.ndarray, n: int = N_REFINE, min_separation_m: float = MIN_SEPARATION_M
) -> np.ndarray:
    """
    Take the best `n` placements, keeping them geographically distinct.

    Neighbouring grid cells score almost identically, so a plain top-n would
    return the same street corner six times over at six rotations. Greedy
    non-maximum suppression keeps the best placement in each area instead,
    which is what makes stage 2's handful of slots worth spending.
    """
    finite = scored[np.isfinite(scored["score"])]
    order = np.argsort(finite["score"])

    chosen: list[np.ndarray] = []
    for idx in order:
        row = finite[idx]
        here = np.array([row["x"], row["y"]])
        if all(np.hypot(*(here - np.array([c["x"], c["y"]]))) >= min_separation_m for c in chosen):
            chosen.append(row)
        if len(chosen) == n:
            break
    return np.array(chosen, dtype=scored.dtype)


# ---------------------------------------------------------------------------
# Stage 2 - run the real POC 2 pipeline on the shortlist
# ---------------------------------------------------------------------------
def refine_placement(
    graph_proj: nx.MultiDiGraph,
    center_xy: np.ndarray,
    rotation_deg: float,
    width_m: float = HEART_WIDTH_M,
    points: int = 40,
    k: int = N_CANDIDATES,
    snap_weight: float = SNAP_WEIGHT,
    deviation_weight: float = DEVIATION_WEIGHT,
) -> dict:
    """
    Fit an actual route to one placement with the POC 2 matcher and score it.

    The coarse pass only knows about proximity to pavement. Everything that
    makes a route walkable rather than merely adjacent to streets - whether the
    streets connect, how far around a block the connection goes, whether the
    matcher has to double back - is decided here.
    """
    heart = place_shape(resample_by_arclength(points), center_xy, width_m, rotation_deg)

    dense = generate_heart_points(4000)
    reference = place_shape(
        np.vstack([dense, dense[:1]]), center_xy, width_m, rotation_deg
    )

    try:
        result = run_poc2(
            graph_proj, heart, reference, k, snap_weight,
            radius_m=260.0, deviation_weight=deviation_weight,
        )
    except NoRouteFoundError:
        # A real outcome of searching a whole city, not a bug: some placements
        # straddle a river or a rail corridor with no walkable crossing. The
        # coarse pass cannot see this - it only measures distance to pavement,
        # never whether the pavement connects.
        return None
    result["center_xy"] = np.asarray(center_xy)
    result["rotation"] = rotation_deg
    result["heart"] = heart
    result["reference"] = reference
    return result


def to_latlon(xy: np.ndarray, crs: str) -> tuple[float, float]:
    """Projected metres back to (lat, lon), for reporting a findable location."""
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(xy[0], xy[1])
    return float(lat), float(lon)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_search_map(
    graph_proj, scored, shortlist, baseline_xy, grid_shape, extent,
    rotations=ROTATIONS_DEG, out_path=OUT_SEARCH,
):
    """Heat map of the coarse score across the city, with the shortlist marked."""
    # Collapse rotations: each cell shows its best achievable score.
    best = scored["score"].reshape(len(rotations), -1).min(axis=0)
    field = np.where(np.isfinite(best), best, np.nan).reshape(grid_shape)

    fig, ax = plt.subplots(figsize=(12, 11))
    ox.plot_graph(graph_proj, ax=ax, node_size=0, edge_color="#e8e8e8",
                  edge_linewidth=0.3, bgcolor="white", show=False, close=False)
    image = ax.imshow(field, origin="lower", extent=extent, cmap="viridis_r",
                      alpha=0.72, zorder=2, interpolation="nearest")
    fig.colorbar(image, ax=ax, shrink=0.75,
                 label="coarse score (m) — lower is better; blank = contour crosses a street-less gap")

    ax.scatter(*baseline_xy, s=170, marker="*", color="#e8443a", edgecolor="black",
               linewidth=0.6, zorder=6, label="POC 1 / 2 hand-picked centre")
    ax.scatter(shortlist["x"], shortlist["y"], s=70, marker="o", color="white",
               edgecolor="black", linewidth=1.2, zorder=6, label="shortlist for stage 2")
    for rank, row in enumerate(shortlist, start=1):
        ax.annotate(str(rank), (row["x"], row["y"]), color="black", fontsize=9,
                    fontweight="bold", ha="center", va="center", zorder=7)

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_title("POC 3 stage 1 — how well do Taipei's streets follow a 2 km heart?", fontsize=13)
    ax.legend(loc="upper right", fontsize=9, facecolor="white", framealpha=0.95)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {out_path}")


def _draw_route(ax, graph_proj, result, title, color):
    ox.plot_graph(graph_proj, ax=ax, node_size=0, edge_color="#dddddd",
                  edge_linewidth=0.4, bgcolor="white", show=False, close=False)
    ref = result["reference"]
    ax.plot(ref[:, 0], ref[:, 1], color="#e8443a", linewidth=1.8, linestyle="--",
            label="Ideal heart contour", zorder=3)
    xy = result["route_xy"]
    ax.plot(xy[:, 0], xy[:, 1], color=color, linewidth=2.6, alpha=0.9,
            label="Actual walking route", zorder=4)

    margin = 320.0
    ax.set_xlim(ref[:, 0].min() - margin, ref[:, 0].max() + margin)
    ax.set_ylim(ref[:, 1].min() - margin, ref[:, 1].max() + margin)
    m = result["metrics"]
    ax.set_title(f"{title}\n{m['route_km']:.2f} km · detour {m['detour_ratio']:.2f}x · "
                 f"chamfer {m['chamfer_m']:.0f} m · {m['backtracked_edges']} backtracked",
                 fontsize=10)
    ax.legend(loc="upper right", fontsize=8, facecolor="white", framealpha=0.9)


def plot_best(graph_proj, best, baseline, out_path=OUT_BEST):
    fig, axes = plt.subplots(1, 2, figsize=(19, 10))
    _draw_route(axes[0], graph_proj, baseline, "POC 2 — hand-picked Da'an centre", "#1a7f37")
    tilt = f" + {best['rotation']:+.0f}° rotation" if best["rotation"] else ""
    _draw_route(axes[1], graph_proj, best, f"POC 3 — searched centre{tilt}", "#6a3d9a")
    fig.suptitle("Hand-picked location vs searched location (same matcher, same 2 km heart)",
                 fontsize=14)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {out_path}")


def plot_top(graph_proj, results, out_path=OUT_TOP):
    n = min(len(results), 6)
    fig, axes = plt.subplots(2, 3, figsize=(21, 14))
    for ax, result, rank in zip(axes.ravel(), results[:n], range(1, n + 1)):
        tilt = f"  ({result['rotation']:+.0f}°)" if result["rotation"] else ""
        _draw_route(ax, graph_proj, result, f"#{rank}{tilt}", "#6a3d9a")
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    fig.suptitle("POC 3 — the shortlist, each fitted with the POC 2 matcher", fontsize=15)
    fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {out_path}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def build_center_grid(center_xy: np.ndarray, half_extent_m: float, step_m: float):
    """Grid of candidate centres, plus the shape and extent needed to plot it."""
    axis = np.arange(-half_extent_m, half_extent_m + step_m, step_m)
    gx, gy = np.meshgrid(center_xy[0] + axis, center_xy[1] + axis)
    centers = np.column_stack([gx.ravel(), gy.ravel()])
    half_cell = step_m / 2.0
    extent = (gx.min() - half_cell, gx.max() + half_cell,
              gy.min() - half_cell, gy.max() + half_cell)
    return centers, gx.shape, extent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=SEARCH_LAT)
    parser.add_argument("--lon", type=float, default=SEARCH_LON)
    parser.add_argument("--half-size-m", type=float, default=NETWORK_HALF_SIZE_M,
                        help="half-side of the searched region, in metres")
    parser.add_argument("--grid-step-m", type=float, default=GRID_STEP_M)
    parser.add_argument("--width-m", type=float, default=HEART_WIDTH_M)
    parser.add_argument("--refine", type=int, default=N_REFINE,
                        help="how many placements reach stage 2")
    parser.add_argument("--rotations", type=str, default=",".join(str(r) for r in ROTATIONS_DEG),
                        help="comma-separated rotations in degrees to search, e.g. '0' or '-10,0,10'")
    args = parser.parse_args()

    print("Loading city-scale walking network")
    graph_proj = download_walk_graph(args.lat, args.lon, args.half_size_m)
    crs = graph_proj.graph["crs"]
    to_proj = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    region_xy = np.array(to_proj.transform(args.lon, args.lat))
    baseline_xy = np.array(to_proj.transform(CENTER_LON, CENTER_LAT))

    print("\nStage 1: coarse scan")
    t0 = time.perf_counter()
    street_tree = build_street_index(graph_proj)

    # Keep the whole heart, plus a margin, inside the downloaded network:
    # placements near the edge would be scored against a truncated street map.
    half_extent = args.half_size_m - args.width_m * 0.75
    centers, grid_shape, extent = build_center_grid(region_xy, half_extent, args.grid_step_m)

    rotations = tuple(int(r) for r in args.rotations.split(","))
    scored = coarse_scan(street_tree, centers, args.width_m, rotations=rotations)
    n_valid = int(np.isfinite(scored["score"]).sum())
    print(f"  scored {len(scored):,} placements ({len(centers):,} centres x "
          f"{len(rotations)} rotations) in {time.perf_counter() - t0:.1f}s")
    print(f"  {n_valid:,} viable, {len(scored) - n_valid:,} rejected for a street-less gap")

    shortlist = select_candidates(scored, args.refine)
    print(f"\n  shortlist (coarse score, lower is better):")
    for rank, row in enumerate(shortlist, start=1):
        lat, lon = to_latlon(np.array([row["x"], row["y"]]), crs)
        print(f"    #{rank}  score {row['score']:5.1f}  mean {row['mean']:5.1f} m  "
              f"p95 {row['p95']:5.1f} m   rot {row['rotation']:+3.0f}°   {lat:.4f}, {lon:.4f}")

    print("\nStage 2: fitting real routes with the POC 2 matcher")
    results = []
    for rank, row in enumerate(shortlist, start=1):
        result = refine_placement(
            graph_proj, np.array([row["x"], row["y"]]), row["rotation"], args.width_m
        )
        if result is None:
            print(f"    #{rank}  infeasible - no closed walking loop at this placement")
            continue
        result["coarse"] = float(row["score"])
        results.append(result)
        m = result["metrics"]
        print(f"    #{rank}  chamfer {m['chamfer_m']:5.1f} m  route {m['route_km']:.2f} km  "
              f"detour {m['detour_ratio']:.2f}x  backtracked {m['backtracked_edges']}")

    # The hand-picked POC 1 / 2 location, refitted on this same graph.
    print("\n  baseline: POC 2's hand-picked Da'an centre, same matcher")
    baseline = refine_placement(graph_proj, baseline_xy, 0.0, args.width_m)
    bm = baseline["metrics"]
    print(f"    chamfer {bm['chamfer_m']:5.1f} m  route {bm['route_km']:.2f} km  "
          f"detour {bm['detour_ratio']:.2f}x  backtracked {bm['backtracked_edges']}")

    # Chamfer is the objective, but placements within CHAMFER_TOLERANCE_M of
    # each other are not meaningfully different shapes - so among those, prefer
    # the one with fewer backtracked edges, since a doubled-back segment is a
    # spur the eye actually notices.
    floor = min(r["metrics"]["chamfer_m"] for r in results)
    results.sort(key=lambda r: (
        r["metrics"]["chamfer_m"] > floor + CHAMFER_TOLERANCE_M,
        r["metrics"]["backtracked_edges"] if r["metrics"]["chamfer_m"] <= floor + CHAMFER_TOLERANCE_M
        else r["metrics"]["chamfer_m"],
    ))
    best = results[0]
    best_lat, best_lon = to_latlon(best["center_xy"], crs)

    print("\nPlotting")
    plot_search_map(graph_proj, scored, shortlist, baseline_xy, grid_shape, extent, rotations)
    plot_best(graph_proj, best, baseline)
    plot_top(graph_proj, results)

    print("\n--- results ---")
    print(f"placements scored        : {len(scored):,}")
    print(f"best location            : {best_lat:.4f}, {best_lon:.4f} "
          f"(rotation {best['rotation']:+.0f}°)")
    print(f"{'metric':<26}{'hand-picked':>14}{'searched':>12}{'change':>10}")
    print("-" * 62)
    rows = [
        ("shape chamfer (m)", "chamfer_m", "{:.1f}", True),
        ("coverage mean (m)", "coverage_mean_m", "{:.1f}", True),
        ("stray mean (m)", "stray_mean_m", "{:.1f}", True),
        ("route distance (km)", "route_km", "{:.2f}", False),
        ("detour ratio", "detour_ratio", "{:.2f}", True),
        ("backtracked edges", "backtracked_edges", "{:.0f}", True),
    ]
    for label, key, fmt, lower_better in rows:
        old, new = bm[key], best["metrics"][key]
        delta = f"{(new - old) / old * 100:+.0f}%" if old else "-"
        mark = ""
        if lower_better and old:
            mark = "  better" if new < old else ("  worse" if new > old else "")
        print(f"{label:<26}{fmt.format(old):>14}{fmt.format(new):>12}{delta:>10}{mark}")


if __name__ == "__main__":
    main()
