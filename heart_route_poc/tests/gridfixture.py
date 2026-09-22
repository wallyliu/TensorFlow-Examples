"""A street network with no map behind it.

Every test that touches the matcher needs a graph. Downloading one would make
the suite depend on Overpass being up, on the proxy, and on a cache file that
is gitignored - so the tests would be slow, flaky, and silent about which of
those three failed. A grid is none of those things, and it is enough: the
matcher only ever asks a graph for node coordinates, edge lengths, degrees and
shortest paths.

It is also the one network whose right answer is known. On a regular grid the
shortest path between two junctions is any staircase between them and its
length is the Manhattan distance, so a test can assert an exact number rather
than "whatever the code returned last time".
"""

from __future__ import annotations

import networkx as nx
import numpy as np

CRS = "EPSG:32651"          # what osmnx picks for Taipei; nothing here depends on it


def grid(n: int = 24, spacing: float = 100.0, origin: tuple = (0.0, 0.0),
         missing: frozenset = frozenset()) -> nx.MultiDiGraph:
    """An n x n Manhattan grid, `spacing` metres apart, as osmnx would hand it over.

    `missing` removes nodes by (i, j), which is how a test builds a barrier: a
    column of missing nodes is a river with no bridge.
    """
    g = nx.MultiDiGraph()
    g.graph["crs"] = CRS
    x0, y0 = origin

    def node(i: int, j: int) -> int:
        return i * n + j

    for i in range(n):
        for j in range(n):
            if (i, j) in missing:
                continue
            g.add_node(node(i, j), x=x0 + i * spacing, y=y0 + j * spacing)

    for i in range(n):
        for j in range(n):
            if (i, j) in missing:
                continue
            for di, dj in ((1, 0), (0, 1)):
                a, b = (i, j), (i + di, j + dj)
                if b[0] >= n or b[1] >= n or b in missing:
                    continue
                # Both directions, because a MultiDiGraph is what osmnx returns
                # and the traversal model for a cyclist is directed.
                g.add_edge(node(*a), node(*b), length=spacing)
                g.add_edge(node(*b), node(*a), length=spacing)
    return g


def square(width_m: float, centre: tuple = (0.0, 0.0), n: int = 40) -> np.ndarray:
    """A closed square, sampled evenly by arc length. Aligned with the grid."""
    half = width_m / 2.0
    corners = np.array([[-half, -half], [half, -half], [half, half], [-half, half]])
    closed = np.vstack([corners, corners[:1]])
    seg = np.hypot(*np.diff(closed, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.linspace(0.0, s[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, s, closed[:, 0]),
                            np.interp(t, s, closed[:, 1])]) + np.asarray(centre)


def circle(radius_m: float, centre: tuple = (0.0, 0.0), n: int = 40) -> np.ndarray:
    """A closed circle. Deliberately NOT alignable with a grid."""
    t = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([np.cos(t), np.sin(t)]) * radius_m + np.asarray(centre)


def centre_of(g: nx.MultiDiGraph) -> tuple:
    xs = [d["x"] for _, d in g.nodes(data=True)]
    ys = [d["y"] for _, d in g.nodes(data=True)]
    return (float(np.mean(xs)), float(np.mean(ys)))
