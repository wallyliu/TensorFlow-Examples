"""
POC 1 - Heart Route on Real Streets (Taipei, Da'an District).

Question this POC answers: can an ideal heart contour be converted into a real
walkable route on Taipei streets that still visually resembles a heart?

Pipeline:
    ideal heart curve (unitless)
      -> scaled/centered onto a metric CRS around a Taipei point
      -> snapped to nearest walkable OSM nodes
      -> consecutive snapped nodes joined by shortest walking paths
      -> plotted against the ideal contour

Run:
    python heart_route_poc.py                 # downloads real OSM data
    python heart_route_poc.py --offline       # synthetic grid, no network needed
"""

import argparse
import math
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Transformer

# Da'an District, Taipei.
DEFAULT_CENTER_LAT = 25.033
DEFAULT_CENTER_LON = 121.543


# ---------------------------------------------------------------------------
# Step 1 - ideal heart contour
# ---------------------------------------------------------------------------


def generate_heart_points(n_points=40, uniform_arclength=True):
    """Return ``n_points`` ordered points along the classic heart curve.

    x(t) = 16 sin(t)^3
    y(t) = 13 cos(t) - 5 cos(2t) - 2 cos(3t) - cos(4t),  t in [0, 2*pi)

    The curve is normalized to a bounding box centered on the origin with
    width exactly 1.0, so the caller controls real-world size with a single
    scale factor.

    Sampling ``t`` uniformly is misleading: the parametric speed drops to zero
    at the top cusp (t=0) and the bottom tip (t=pi), so uniform-in-t points
    pile up at those two features and starve the lobes. We therefore resample
    at constant arc length, which spreads the samples evenly around the
    outline and gives the snapping step even coverage of the contour.
    """
    t_dense = np.linspace(0.0, 2.0 * np.pi, 4000)
    x_dense = 16.0 * np.sin(t_dense) ** 3
    y_dense = (
        13.0 * np.cos(t_dense)
        - 5.0 * np.cos(2.0 * t_dense)
        - 2.0 * np.cos(3.0 * t_dense)
        - np.cos(4.0 * t_dense)
    )

    if uniform_arclength:
        # Cumulative chord length along the densely sampled outline, then pick
        # n_points positions equally spaced in arc length (open interval, so
        # the contour stays a closed loop without a duplicated first point).
        steps = np.hypot(np.diff(x_dense), np.diff(y_dense))
        arc = np.concatenate([[0.0], np.cumsum(steps)])
        targets = np.linspace(0.0, arc[-1], n_points, endpoint=False)
        x = np.interp(targets, arc, x_dense)
        y = np.interp(targets, arc, y_dense)
    else:
        t = np.linspace(0.0, 2.0 * np.pi, n_points, endpoint=False)
        x = 16.0 * np.sin(t) ** 3
        y = (
            13.0 * np.cos(t)
            - 5.0 * np.cos(2.0 * t)
            - 2.0 * np.cos(3.0 * t)
            - np.cos(4.0 * t)
        )

    # Normalize against the full curve's bounding box (not the sample's), so
    # the result is independent of n_points.
    x_span = x_dense.max() - x_dense.min()
    x_mid = 0.5 * (x_dense.max() + x_dense.min())
    y_mid = 0.5 * (y_dense.max() + y_dense.min())
    return np.column_stack([(x - x_mid) / x_span, (y - y_mid) / x_span])


# ---------------------------------------------------------------------------
# Step 2 - place the heart on the map
# ---------------------------------------------------------------------------


def ideal_perimeter(width_m):
    """Arc length of the ideal heart outline, in metres, at a given width.

    Baseline for the detour ratio: how much longer the street route is than
    the shape it is imitating.
    """
    t = np.linspace(0.0, 2.0 * np.pi, 4000)
    x = 16.0 * np.sin(t) ** 3
    y = 13.0 * np.cos(t) - 5.0 * np.cos(2 * t) - 2.0 * np.cos(3 * t) - np.cos(4 * t)
    unit = np.hypot(np.diff(x), np.diff(y)).sum() / (x.max() - x.min())
    return unit * width_m


def utm_crs_for(lat, lon):
    """EPSG code of the UTM zone containing (lat, lon). Taipei -> 32651."""
    zone = int((lon + 180.0) / 6.0) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def transform_shape_to_map(shape, center_lat, center_lon, width_m):
    """Place a normalized shape onto the map, in projected metres.

    All geometry is done in a UTM CRS rather than in degrees: one metre east
    and one metre north are the same size there, so the heart keeps its aspect
    ratio. Working directly in lat/lon would squash it horizontally, since a
    degree of longitude at 25N is only ~0.906 of a degree of latitude.
    """
    crs = utm_crs_for(center_lat, center_lon)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    cx, cy = to_utm.transform(center_lon, center_lat)

    xs = cx + shape[:, 0] * width_m
    ys = cy + shape[:, 1] * width_m
    return xs, ys, crs


# ---------------------------------------------------------------------------
# Step 3 - walking street network
# ---------------------------------------------------------------------------


def download_walk_graph(center_lat, center_lon, dist_m, crs):
    """Download the walkable OSM network around the centre, projected to ``crs``."""
    print(f"Downloading walk network within {dist_m} m of "
          f"({center_lat}, {center_lon}) ...")
    graph = ox.graph_from_point(
        (center_lat, center_lon), dist=dist_m, network_type="walk", simplify=True
    )
    # Project to the same CRS as the heart so snapping is a plain metric
    # nearest-neighbour lookup.
    return ox.project_graph(graph, to_crs=crs)


def synthetic_walk_graph(center_lat, center_lon, dist_m, crs, seed=7):
    """Offline stand-in for OSM: a Da'an-like grid in projected metres.

    Da'an is a fairly regular grid of ~400 m arterial blocks subdivided by
    ~100 m lanes and alleys, many of which do not run through. This mimics
    that: arterials always connect, minor lane segments survive with p=0.6.
    Useful for exercising the pipeline where OSM cannot be reached; it is not
    a substitute for real data.
    """
    print(f"[offline] Building synthetic {dist_m} m grid network "
          f"(no OSM download).")
    rng = np.random.default_rng(seed)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    cx, cy = to_utm.transform(center_lon, center_lat)

    minor, major_every = 100.0, 4  # 100 m lanes, arterial every 4th line
    n = int(dist_m / minor)
    idx = range(-n, n + 1)

    graph = nx.MultiDiGraph(crs=crs, simplified=True)
    node_id = {}
    for i in idx:
        for j in idx:
            nid = len(node_id)
            node_id[(i, j)] = nid
            # Jitter so the grid is not perfectly regular, as real streets are not.
            graph.add_node(
                nid,
                x=cx + i * minor + rng.uniform(-12, 12),
                y=cy + j * minor + rng.uniform(-12, 12),
            )

    def add_edge(a, b):
        ax, ay = graph.nodes[a]["x"], graph.nodes[a]["y"]
        bx, by = graph.nodes[b]["x"], graph.nodes[b]["y"]
        length = math.hypot(bx - ax, by - ay)
        graph.add_edge(a, b, length=length)
        graph.add_edge(b, a, length=length)

    for i in idx:
        for j in idx:
            for di, dj in ((1, 0), (0, 1)):
                ni, nj = i + di, j + dj
                if (ni, nj) not in node_id:
                    continue
                # A segment is arterial if it runs along a major line.
                arterial = (j % major_every == 0) if di else (i % major_every == 0)
                if arterial or rng.random() < 0.6:
                    add_edge(node_id[(i, j)], node_id[(ni, nj)])

    largest = max(nx.weakly_connected_components(graph), key=len)
    return graph.subgraph(largest).copy()


# ---------------------------------------------------------------------------
# Step 4 - snap ideal points to the network
# ---------------------------------------------------------------------------


def snap_points_to_graph(graph, xs, ys, drop_consecutive_duplicates=True):
    """Snap each ideal point to its nearest walkable node.

    Returns ``(nodes, snap_distances)`` where ``nodes[i]`` is the node chosen
    for ideal point ``i``. Several ideal points can legitimately land on the
    same node where the street network is sparse; consecutive repeats are
    collapsed because routing a node to itself contributes nothing but does
    distort the "unique nodes" reading.
    """
    nodes = ox.distance.nearest_nodes(graph, X=xs, Y=ys)
    nodes = [int(v) for v in np.atleast_1d(nodes)]

    dists = [
        math.hypot(graph.nodes[n]["x"] - x, graph.nodes[n]["y"] - y)
        for n, x, y in zip(nodes, xs, ys)
    ]

    if drop_consecutive_duplicates:
        kept = [i for i in range(len(nodes)) if nodes[i] != nodes[i - 1]]
        nodes = [nodes[i] for i in kept]
        dists = [dists[i] for i in kept]

    return nodes, np.asarray(dists)


# ---------------------------------------------------------------------------
# Step 5 - connect snapped points into a closed route
# ---------------------------------------------------------------------------


def build_route(graph, nodes):
    """Shortest walking path between each consecutive pair, closing the loop.

    Returns ``(legs, failed, total_m)``. ``legs`` is a list of node sequences
    rather than one flat path so that an unreachable pair leaves a visible gap
    instead of a fake straight line across the map.
    """
    legs, failed, total = [], [], 0.0

    for i, origin in enumerate(nodes):
        target = nodes[(i + 1) % len(nodes)]  # wraps: closes the contour
        try:
            path = nx.shortest_path(graph, origin, target, weight="length")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            failed.append((i, (i + 1) % len(nodes)))
            continue
        legs.append(path)
        total += path_length(graph, path)

    return legs, failed, total


def path_length(graph, path):
    """Metres along a node path, taking the shortest of any parallel edges."""
    total = 0.0
    for a, b in zip(path[:-1], path[1:]):
        total += min(d["length"] for d in graph[a][b].values())
    return total


def leg_coords(graph, leg):
    """(xs, ys) along a node path, following real street geometry.

    OSMnx simplification collapses a curving street into a single edge that
    carries a ``geometry`` LineString. Drawing node-to-node straight lines
    would cut those curves, so use the geometry where it exists. Stored
    geometry is not guaranteed to run u->v, so flip it when the far end is
    closer to u.
    """
    xs, ys = [], []
    for a, b in zip(leg[:-1], leg[1:]):
        data = min(graph[a][b].values(), key=lambda d: d["length"])
        geom = data.get("geometry")
        if geom is None:
            px, py = [graph.nodes[a]["x"], graph.nodes[b]["x"]], \
                     [graph.nodes[a]["y"], graph.nodes[b]["y"]]
        else:
            px, py = list(geom.xy[0]), list(geom.xy[1])
            ax_, ay_ = graph.nodes[a]["x"], graph.nodes[a]["y"]
            if math.hypot(px[0] - ax_, py[0] - ay_) > \
               math.hypot(px[-1] - ax_, py[-1] - ay_):
                px, py = px[::-1], py[::-1]
        xs.extend(px[:-1])
        ys.extend(py[:-1])
    xs.append(graph.nodes[leg[-1]]["x"])
    ys.append(graph.nodes[leg[-1]]["y"])
    return xs, ys


def densify(px, py, step=10.0):
    """Resample a polyline at roughly ``step`` metres for distance comparisons."""
    out = []
    for (x0, y0), (x1, y1) in zip(zip(px, py), zip(px[1:], py[1:])):
        n = max(int(math.hypot(x1 - x0, y1 - y0) / step), 1)
        out.extend(zip(np.linspace(x0, x1, n, endpoint=False),
                       np.linspace(y0, y1, n, endpoint=False)))
    out.append((px[-1], py[-1]))
    return np.asarray(out)


def shape_deviation(graph, legs, center_lat, center_lon, width_m):
    """How far the drawn route strays from the ideal heart, in metres.

    Route length alone is a bad quality score - dropping waypoints shortens
    the route while making the drawing worse. This measures the thing we
    actually care about, symmetrically:

      route -> ideal   catches route excursions that bulge off the shape
      ideal -> route   catches parts of the heart the route never draws

    Returns (mean, p95) over both directions combined.
    """
    from scipy.spatial import cKDTree

    dense_shape = generate_heart_points(2000)
    ix, iy, _ = transform_shape_to_map(dense_shape, center_lat, center_lon, width_m)
    ideal = np.column_stack([np.append(ix, ix[0]), np.append(iy, iy[0])])

    route = np.vstack([densify(*leg_coords(graph, leg)) for leg in legs])

    d1, _ = cKDTree(ideal).query(route)
    d2, _ = cKDTree(route).query(ideal)
    both = np.concatenate([d1, d2])
    return float(both.mean()), float(np.percentile(both, 95))


# ---------------------------------------------------------------------------
# Step 6 - visualise
# ---------------------------------------------------------------------------


def plot_ideal_shape(shape, path):
    """Sanity check that the parametric curve really looks like a heart."""
    fig, ax = plt.subplots(figsize=(5, 5))
    loop = np.vstack([shape, shape[:1]])
    ax.plot(loop[:, 0], loop[:, 1], "-", color="crimson", lw=1.5)
    ax.plot(shape[:, 0], shape[:, 1], "o", color="crimson", ms=4)
    ax.set_aspect("equal")
    ax.set_title(f"Step 1: ideal heart contour ({len(shape)} points)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"Wrote {path}")


def plot_result(graph, xs, ys, nodes, legs, stats, path):
    """Street network + ideal contour + snapped nodes + actual walking route."""
    fig, ax = plt.subplots(figsize=(11, 11))
    ox.plot_graph(
        graph,
        ax=ax,
        node_size=0,
        edge_color="#d9d9d9",
        edge_linewidth=0.5,
        bgcolor="white",
        show=False,
        close=False,
    )

    ideal_x = np.append(xs, xs[0])
    ideal_y = np.append(ys, ys[0])
    ax.plot(ideal_x, ideal_y, "--", color="crimson", lw=2.0,
            label="Ideal heart contour", zorder=3)

    for i, leg in enumerate(legs):
        lx, ly = leg_coords(graph, leg)
        ax.plot(lx, ly, "-", color="#1f77b4", lw=3.0, alpha=0.9, zorder=4,
                label="Actual walking route" if i == 0 else None)

    ax.scatter(
        [graph.nodes[n]["x"] for n in nodes],
        [graph.nodes[n]["y"] for n in nodes],
        s=34, color="darkorange", edgecolor="white", linewidth=0.6,
        zorder=5, label="Snapped road nodes",
    )

    # Zoom to the heart plus a margin; the downloaded graph is much larger.
    pad = 0.25 * (xs.max() - xs.min())
    ax.set_xlim(xs.min() - pad, xs.max() + pad)
    ax.set_ylim(ys.min() - pad, ys.max() + pad)
    ax.set_title(stats["title"], fontsize=13)
    ax.legend(loc="upper right", framealpha=0.95)
    ax.text(
        0.02, 0.02, stats["text"], transform=ax.transAxes, fontsize=9,
        va="bottom", ha="left", family="monospace",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.9),
    )

    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"Wrote {path}")


# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=DEFAULT_CENTER_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_CENTER_LON)
    parser.add_argument("--points", type=int, default=36,
                        help="heart contour samples (30-50 suggested)")
    parser.add_argument("--width-km", type=float, default=2.0,
                        help="target heart width in km")
    parser.add_argument("--radius-km", type=float, default=3.5,
                        help="network download radius in km")
    parser.add_argument("--offline", action="store_true",
                        help="use a synthetic grid instead of downloading OSM")
    parser.add_argument("--keep-duplicate-nodes", action="store_true",
                        help="do not collapse consecutive duplicate snaps")
    parser.add_argument("--out", default="heart_route_poc.png")
    args = parser.parse_args()

    # Step 1
    shape = generate_heart_points(args.points)
    plot_ideal_shape(shape, "heart_shape_check.png")

    # Step 2
    xs, ys, crs = transform_shape_to_map(
        shape, args.lat, args.lon, args.width_km * 1000.0
    )

    # Step 3
    dist_m = int(args.radius_km * 1000)
    if args.offline:
        graph = synthetic_walk_graph(args.lat, args.lon, dist_m, crs)
    else:
        try:
            graph = download_walk_graph(args.lat, args.lon, dist_m, crs)
        except Exception as exc:  # network/Overpass problems are common
            print(f"\nCould not download the OSM network: {exc}\n"
                  "Check connectivity to overpass-api.de, or rerun with "
                  "--offline to exercise the pipeline on a synthetic grid.",
                  file=sys.stderr)
            return 1

    print(f"Graph: {graph.number_of_nodes()} nodes, "
          f"{graph.number_of_edges()} edges, CRS {crs}")

    # Steps 4 and 5
    nodes, snap_dists = snap_points_to_graph(
        graph, xs, ys, drop_consecutive_duplicates=not args.keep_duplicate_nodes
    )
    legs, failed, total_m = build_route(graph, nodes)

    ideal_m = ideal_perimeter(args.width_km * 1000.0)
    spacing_m = ideal_m / len(shape)
    dev_mean, dev_p95 = shape_deviation(
        graph, legs, args.lat, args.lon, args.width_km * 1000.0
    )

    print("\n--- POC results ---")
    print(f"heart sample points      : {len(shape)}")
    print(f"unique snapped nodes     : {len(set(nodes))}")
    print(f"total route distance     : {total_m / 1000.0:.2f} km")
    print(f"failed/unreachable legs  : {len(failed)}")
    print(f"snap distance mean / max : {snap_dists.mean():.0f} m / "
          f"{snap_dists.max():.0f} m")
    print(f"ideal contour perimeter  : {ideal_m / 1000.0:.2f} km "
          f"({spacing_m:.0f} m between samples)")
    print(f"detour ratio             : {total_m / ideal_m:.2f}x")
    print(f"shape deviation mean/p95 : {dev_mean:.0f} m / {dev_p95:.0f} m")
    if failed:
        print(f"failed pairs             : {failed}")

    # Step 6
    stats = {
        "title": (f"Heart route POC - Taipei Da'an "
                  f"({args.lat}, {args.lon})"
                  + ("  [SYNTHETIC GRID]" if args.offline else "")),
        "text": (
            f"heart points      : {len(shape)}\n"
            f"unique snap nodes : {len(set(nodes))}\n"
            f"route distance    : {total_m / 1000.0:.2f} km\n"
            f"failed legs       : {len(failed)}\n"
            f"snap dist mean/max: {snap_dists.mean():.0f}/{snap_dists.max():.0f} m\n"
            f"ideal perimeter   : {ideal_m / 1000.0:.2f} km\n"
            f"detour ratio      : {total_m / ideal_m:.2f}x\n"
            f"shape dev mean/p95: {dev_mean:.0f}/{dev_p95:.0f} m"
        ),
    }
    plot_result(graph, xs, ys, nodes, legs, stats, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
