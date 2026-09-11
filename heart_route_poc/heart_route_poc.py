"""
POC 1 - Heart Route on Real Streets
===================================

Question this POC answers, and nothing more:

    Can an ideal heart shape be turned into a real walkable route on Taipei
    streets that still visually reads as a heart?

Pipeline:

    1. Sample an ideal heart contour from a parametric equation.
    2. Place and scale that contour over Da'an District, Taipei.
    3. Download the surrounding walkable street network from OpenStreetMap.
    4. Snap each contour point to the nearest walkable road node.
    5. Shortest-path between consecutive snapped nodes, closing the loop.
    6. Plot the ideal contour against the actual route and report metrics.

Run:  python heart_route_poc.py
Out:  heart_route_poc.png
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless-safe; must precede pyplot import
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Transformer

# osmnx keeps a short default list of way tags and drops the rest, and `bicycle`
# is not on it. Every rideability audit in POC 10 therefore read a field that did
# not exist and counted every pavement as off-limits, when 14% of Taipei's are
# signed for shared use. The filters were right; the analysis was reading blanks.
ox.settings.useful_tags_way = list(dict.fromkeys(
    list(ox.settings.useful_tags_way)
    + ["bicycle", "cycleway", "foot", "surface", "segregated", "incline"]
))
from scipy.spatial import cKDTree

# ---------------------------------------------------------------------------
# Configuration - the only knobs this POC exposes.
# ---------------------------------------------------------------------------
CENTER_LAT = 25.033          # Da'an District, Taipei
CENTER_LON = 121.543
HEART_WIDTH_M = 2000.0       # target width of the heart on the ground
N_HEART_POINTS = 40          # samples along the ideal contour
NETWORK_HALF_SIZE_M = 2000.0 # half-side of the square network box (4 km x 4 km)
OUTPUT_PNG = Path(__file__).with_name("heart_route_poc.png")
CACHE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Step 1 - ideal heart contour
# ---------------------------------------------------------------------------
def generate_heart_points(n_points: int = N_HEART_POINTS) -> np.ndarray:
    """
    Sample the classic parametric heart curve.

        x = 16 sin(t)^3
        y = 13 cos(t) - 5 cos(2t) - 2 cos(3t) - cos(4t)

    Returns an (n_points, 2) array of ordered points, normalised so the shape
    is centred on its own bounding box and spans exactly 1.0 in width. Keeping
    the width fixed (rather than normalising both axes) preserves the heart's
    aspect ratio, so scaling later is a single multiply.

    `t` is sampled on [0, 2*pi) with `endpoint=False`: the curve is closed, so
    including 2*pi would duplicate the point at t=0.
    """
    t = np.linspace(0.0, 2.0 * np.pi, n_points, endpoint=False)
    x = 16.0 * np.sin(t) ** 3
    y = 13.0 * np.cos(t) - 5.0 * np.cos(2 * t) - 2.0 * np.cos(3 * t) - np.cos(4 * t)

    # Centre on the bounding-box midpoint and divide both axes by the width,
    # which keeps x in [-0.5, 0.5] and lets y run to whatever the aspect ratio
    # demands (about +-0.45 for this curve).
    x_centred = x - (x.max() + x.min()) / 2.0
    y_centred = y - (y.max() + y.min()) / 2.0
    width = x.max() - x.min()
    return np.column_stack([x_centred / width, y_centred / width])


# ---------------------------------------------------------------------------
# Step 2 - place the shape on the map
# ---------------------------------------------------------------------------
def transform_shape_to_map(
    shape: np.ndarray,
    center_lat: float,
    center_lon: float,
    width_m: float,
    crs: str,
) -> np.ndarray:
    """
    Scale the normalised shape to `width_m` metres and centre it on the given
    lat/lon, expressed in the projected CRS `crs`.

    All geometry is done in a metric CRS rather than in degrees. A degree of
    longitude in Taipei is only ~0.906 of a degree of latitude, so offsetting
    in raw degrees would squash the heart horizontally by ~10%. Projecting
    first makes "1 unit east" and "1 unit north" both mean one metre.

    Returns an (n, 2) array of (x, y) coordinates in `crs`.
    """
    to_proj = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    center_x, center_y = to_proj.transform(center_lon, center_lat)
    return np.column_stack([
        center_x + shape[:, 0] * width_m,
        center_y + shape[:, 1] * width_m,
    ])


def projected_to_latlon(points_proj: np.ndarray, crs: str) -> np.ndarray:
    """Convert (x, y) in `crs` back to (lat, lon), for printing and sanity checks."""
    to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lon, lat = to_wgs84.transform(points_proj[:, 0], points_proj[:, 1])
    return np.column_stack([lat, lon])


# ---------------------------------------------------------------------------
# Step 3 - street network
# ---------------------------------------------------------------------------
def download_walk_graph(
    center_lat: float = CENTER_LAT,
    center_lon: float = CENTER_LON,
    half_size_m: float = NETWORK_HALF_SIZE_M,
    mode: str = "walk",
) -> nx.MultiDiGraph:
    """
    Download the usable street network around the centre and project it to a
    metric CRS (UTM zone 51N for Taipei, chosen automatically by osmnx).

    `mode` is "walk" or "bike", and it changes two things, not one. The filter
    differs - a bicycle may not use a pavement or a flight of steps - and so
    does the traversal model: a pedestrian ignores one-way restrictions and a
    cyclist does not. Getting the second one wrong would produce routes that
    look legal and ride the wrong way up 8,000 one-way streets.

    The primary path is osmnx's usual Overpass query. Some sandboxed networks
    block every Overpass mirror; in that case this falls back to tiling the
    official OSM Map API (see osm_api_fallback.py). The fallback produces the
    same kind of graph, just over a square box instead of a disc.
    """
    bidirectional = mode == "walk"
    # Key the cache on the actual area, so changing --lat/--lon fetches a new
    # network instead of silently reusing the previous one.
    cache_xml = CACHE_DIR / f"_{mode}_{center_lat:.4f}_{center_lon:.4f}_{half_size_m:.0f}m.osm"

    if cache_xml.exists():
        print(f"  using cached network file {cache_xml.name}")
        graph = ox.graph_from_xml(cache_xml, bidirectional=bidirectional, simplify=True)
    else:
        try:
            # dist is the half-side of a square bbox, matching the fallback.
            graph = ox.graph_from_point(
                (center_lat, center_lon),
                dist=half_size_m,
                network_type=mode,
                simplify=True,
            )
        except Exception as exc:  # noqa: BLE001 - Overpass unreachable, not a bug
            print(f"  Overpass unavailable ({type(exc).__name__}: {exc})")
            print("  falling back to the OSM Map API tiler")
            from osm_api_fallback import download_network_xml

            download_network_xml(center_lat, center_lon, half_size_m, cache_xml, mode)
            graph = ox.graph_from_xml(cache_xml, bidirectional=bidirectional, simplify=True)

    graph_proj = ox.project_graph(graph)
    print(f"  network: {graph_proj.number_of_nodes()} nodes, "
          f"{graph_proj.number_of_edges()} edges, CRS {graph_proj.graph['crs']}")
    return graph_proj


# ---------------------------------------------------------------------------
# Step 4 - snap contour points to the network
# ---------------------------------------------------------------------------
def snap_points_to_graph(
    graph_proj: nx.MultiDiGraph,
    points_proj: np.ndarray,
    unique: bool = True,
    min_degree: int = 3,
) -> tuple[list[int], np.ndarray]:
    """
    Map each ideal contour point to a nearby walkable road node.

    Two refinements over a plain nearest-node lookup, both added after looking
    at the first run's output (see README "What we changed and why"):

    `min_degree` drops dead ends from the candidate pool. A degree-1 node sits
    at the end of a cul-de-sac, a footway stub or a flight of steps, so the only
    way in is also the only way out - routing through one forces a visible
    out-and-back spur. Measured on the baseline run, 5 of 40 targets were
    degree-1 nodes and they caused most of the doubled-back edges. Degree-2
    nodes are mid-block points that osmnx's simplification mostly removes
    already, so requiring degree >= 3 keeps targets at real junctions.

    `unique` stops two contour points from claiming the same node, which would
    silently drop a sample from the shape. It walks outward through the k
    nearest candidates until it finds an unused one.

    Returns the snapped node ids (parallel to `points_proj`) and each point's
    snap distance in metres.
    """
    candidates = [n for n, deg in graph_proj.to_undirected().degree() if deg >= min_degree]
    if not candidates:  # pathological graph; fall back to every node
        candidates = list(graph_proj.nodes)

    node_xy = np.array([[graph_proj.nodes[n]["x"], graph_proj.nodes[n]["y"]] for n in candidates])
    tree = cKDTree(node_xy)

    # Query several neighbours per point so `unique` has somewhere to go.
    k = min(30, len(candidates))
    dists, idxs = tree.query(points_proj, k=k)
    if k == 1:  # cKDTree squeezes the axis when k == 1
        dists, idxs = dists[:, None], idxs[:, None]

    snapped: list[int] = []
    snap_dist: list[float] = []
    used: set[int] = set()
    for row_d, row_i in zip(dists, idxs):
        for dist, idx in zip(row_d, row_i):
            node = candidates[idx]
            if not unique or node not in used:
                used.add(node)
                snapped.append(node)
                snap_dist.append(float(dist))
                break
        else:
            # All k neighbours taken - accept the nearest and allow the repeat.
            snapped.append(candidates[row_i[0]])
            snap_dist.append(float(row_d[0]))

    return snapped, np.array(snap_dist)


# ---------------------------------------------------------------------------
# Step 5 - connect the snapped points
# ---------------------------------------------------------------------------
def build_route(
    graph_proj: nx.MultiDiGraph, snapped_nodes: list[int]
) -> tuple[list[int], float, list[tuple[int, int]]]:
    """
    Walk the ordered snapped nodes, shortest-pathing between each consecutive
    pair and wrapping from the last point back to the first to close the loop.

    Consecutive duplicates are skipped: when two ideal points land on the same
    node there is nothing to route. Segments with no path are recorded and
    stepped over rather than aborting the run.

    Returns the concatenated node sequence, the total length in metres, and the
    list of (u, v) pairs that had no connecting path.
    """
    # Collapse consecutive duplicates while keeping the loop order intact.
    ordered = [snapped_nodes[0]]
    for node in snapped_nodes[1:]:
        if node != ordered[-1]:
            ordered.append(node)
    if len(ordered) > 1 and ordered[-1] == ordered[0]:
        ordered.pop()

    route: list[int] = []
    total_m = 0.0
    failures: list[tuple[int, int]] = []

    for i in range(len(ordered)):
        u = ordered[i]
        v = ordered[(i + 1) % len(ordered)]  # wraps: closes the loop
        try:
            leg = nx.shortest_path(graph_proj, u, v, weight="length")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            failures.append((u, v))
            continue
        total_m += _path_length_m(graph_proj, leg)
        # Drop the first node of each leg after the first: it repeats the
        # previous leg's endpoint.
        route.extend(leg if not route else leg[1:])

    return route, total_m, failures


def route_quality(
    graph_proj: nx.MultiDiGraph, route: list[int], heart_proj: np.ndarray, total_m: float
) -> dict[str, float]:
    """
    Two cheap numbers that say how much fidelity the street network cost us.

    `detour_ratio` compares the route against the ideal contour's own
    perimeter: 1.0 would mean the streets traced the heart exactly, and
    anything above that is the street grid forcing longer paths.

    `backtracked_edges` counts road segments the route walks more than once.
    Each one is a visible out-and-back spur on the plot, so this is the direct
    measure of the POC's main visual artifact.
    """
    closed = np.vstack([heart_proj, heart_proj[:1]])
    perimeter_m = float(np.hypot(*np.diff(closed, axis=0).T).sum())

    seen = Counter(frozenset((u, v)) for u, v in zip(route[:-1], route[1:]))
    backtracked = sum(count - 1 for count in seen.values() if count > 1)

    return {
        "ideal_perimeter_km": perimeter_m / 1000.0,
        "detour_ratio": total_m / perimeter_m if perimeter_m else float("nan"),
        "backtracked_edges": backtracked,
        "route_edges": max(len(route) - 1, 0),
    }


def _path_length_m(graph_proj: nx.MultiDiGraph, path: list[int]) -> float:
    """Sum edge lengths along a node path, taking the shortest parallel edge."""
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        total += min(d["length"] for d in graph_proj[u][v].values())
    return total


# ---------------------------------------------------------------------------
# Step 6 - visualise
# ---------------------------------------------------------------------------
def plot_result(
    graph_proj: nx.MultiDiGraph,
    heart_proj: np.ndarray,
    snapped_nodes: list[int],
    route: list[int],
    out_path: Path = OUTPUT_PNG,
) -> None:
    """Draw the street network, the ideal contour, the snap targets and the route."""
    fig, ax = ox.plot_graph(
        graph_proj,
        node_size=0,
        edge_color="#d9d9d9",
        edge_linewidth=0.5,
        bgcolor="white",
        show=False,
        close=False,
        figsize=(11, 11),
    )

    # Ideal contour - closed by repeating the first point.
    ideal_closed = np.vstack([heart_proj, heart_proj[:1]])
    ax.plot(ideal_closed[:, 0], ideal_closed[:, 1],
            color="#e8443a", linewidth=2.2, linestyle="--",
            label="Ideal heart contour", zorder=3)

    # Actual route on the street network.
    route_xy = np.array([[graph_proj.nodes[n]["x"], graph_proj.nodes[n]["y"]] for n in route])
    ax.plot(route_xy[:, 0], route_xy[:, 1],
            color="#1f6fb4", linewidth=2.6, alpha=0.9,
            label="Actual walking route", zorder=4)

    # Snapped target nodes.
    snap_xy = np.array([[graph_proj.nodes[n]["x"], graph_proj.nodes[n]["y"]]
                        for n in snapped_nodes])
    ax.scatter(snap_xy[:, 0], snap_xy[:, 1],
               s=26, color="#f6a800", edgecolor="black", linewidth=0.4,
               label="Snapped road nodes", zorder=5)

    # Frame the heart with a margin instead of showing the whole downloaded box.
    margin = 350.0
    ax.set_xlim(heart_proj[:, 0].min() - margin, heart_proj[:, 0].max() + margin)
    ax.set_ylim(heart_proj[:, 1].min() - margin, heart_proj[:, 1].max() + margin)
    ax.set_title("POC 1 - Heart route on Taipei walking streets (Da'an District)",
                 color="black", fontsize=13)
    ax.legend(loc="upper right", facecolor="white", framealpha=0.9)

    fig.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {out_path}")


def plot_ideal_heart(shape: np.ndarray, out_path: Path) -> None:
    """Sanity check for Step 1: plot the normalised contour on its own."""
    closed = np.vstack([shape, shape[:1]])
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(closed[:, 0], closed[:, 1], color="#e8443a", linewidth=2)
    ax.scatter(shape[:, 0], shape[:, 1], s=14, color="#e8443a")
    ax.set_aspect("equal")
    ax.set_title(f"Ideal heart contour ({len(shape)} points)")
    fig.savefig(out_path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {out_path}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=int, default=N_HEART_POINTS,
                        help="number of ideal heart contour samples")
    parser.add_argument("--width-m", type=float, default=HEART_WIDTH_M,
                        help="target heart width on the ground, in metres")
    parser.add_argument("--lat", type=float, default=CENTER_LAT)
    parser.add_argument("--lon", type=float, default=CENTER_LON)
    parser.add_argument("--out", type=Path, default=OUTPUT_PNG)
    parser.add_argument("--allow-dead-ends", action="store_true",
                        help="allow degree-1 nodes as snap targets (the pre-tuning baseline)")
    parser.add_argument("--allow-duplicate-snaps", action="store_true",
                        help="let several contour points snap to the same node")
    args = parser.parse_args()

    print("Step 1: generating ideal heart contour")
    shape = generate_heart_points(args.points)
    plot_ideal_heart(shape, args.out.with_name("ideal_heart.png"))

    print("Step 3: downloading walking network")
    graph_proj = download_walk_graph(args.lat, args.lon)
    crs = graph_proj.graph["crs"]

    print("Step 2: placing the heart over Taipei")
    heart_proj = transform_shape_to_map(shape, args.lat, args.lon, args.width_m, crs)
    heart_latlon = projected_to_latlon(heart_proj, crs)
    print(f"  heart spans lat {heart_latlon[:, 0].min():.5f}..{heart_latlon[:, 0].max():.5f}, "
          f"lon {heart_latlon[:, 1].min():.5f}..{heart_latlon[:, 1].max():.5f}")

    print("Step 4: snapping contour points to road nodes")
    snapped_nodes, snap_dist = snap_points_to_graph(
        graph_proj,
        heart_proj,
        unique=not args.allow_duplicate_snaps,
        min_degree=1 if args.allow_dead_ends else 3,
    )

    print("Step 5: routing between consecutive points")
    route, total_m, failures = build_route(graph_proj, snapped_nodes)

    quality = route_quality(graph_proj, route, heart_proj, total_m)

    print("Step 6: plotting")
    plot_result(graph_proj, heart_proj, snapped_nodes, route, args.out)

    print("\n--- results ---")
    print(f"heart sample points      : {len(shape)}")
    print(f"unique snapped nodes     : {len(set(snapped_nodes))}")
    print(f"total route distance     : {total_m / 1000:.2f} km")
    print(f"failed segments          : {len(failures)}")
    print(f"snap distance mean/max   : {snap_dist.mean():.0f} m / {snap_dist.max():.0f} m")
    print(f"route node count         : {len(route)}")
    print(f"ideal contour perimeter  : {quality['ideal_perimeter_km']:.2f} km")
    print(f"detour ratio vs ideal    : {quality['detour_ratio']:.2f}x")
    print(f"backtracked edges        : {quality['backtracked_edges']} "
          f"of {quality['route_edges']} (out-and-back spurs)")
    if failures:
        print(f"unreachable pairs        : {failures}")


if __name__ == "__main__":
    main()
