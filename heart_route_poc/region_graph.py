"""
Build a street network for anywhere in a downloaded region, without downloading.

`download_walk_graph` keys its cache on the exact centre and radius, so asking
for a box 500 m to the left is a cache miss and another nine-minute download.
That was fine while there was one city and one box. It does not survive "let
the user pick where they are", which needs an arbitrary box anywhere in the
region.

`region_download.py` leaves the region on disk as overlapping tiles. This
stitches whichever of them touch the box you ask for into one graph: read the
tiles, drop duplicate nodes and ways by id, clip to the box, write one XML,
hand it to osmnx. The merged file is cached under a name derived from the box,
so asking twice costs once.

Tiles do not line up with the box, so the result covers MORE than asked for at
the edges. That is deliberate - clipping ways at the boundary would leave the
route dangling on stubs that stop in mid-air - and the extra is trimmed by
bounding box on the nodes, not on the ways.

Run:  python region_graph.py --lat 25.04 --lon 121.54 --half-size 7000
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from xml.sax.saxutils import quoteattr

import networkx as nx
import osmnx as ox

from region_download import CACHE_ROOT, REGIONS

MERGED_DIR = Path(__file__).with_name("_region_merged")
TILE_NAME = re.compile(r"^(-?\d+\.\d+)_(-?\d+\.\d+)_(-?\d+\.\d+)_(-?\d+\.\d+)\.osm$")


def tile_bounds(path: Path):
    """South, west, north, east - the order region_download names them in."""
    m = TILE_NAME.match(path.name)
    if not m:
        return None
    south, west, north, east = (float(v) for v in m.groups())
    return south, west, north, east


def box_around(lat: float, lon: float, half_size_m: float):
    d_lat = half_size_m / 111_320.0
    d_lon = half_size_m / (111_320.0 * math.cos(math.radians(lat)))
    return lat - d_lat, lon - d_lon, lat + d_lat, lon + d_lon


def tiles_for(box, region: str, mode: str) -> list[Path]:
    """Every cached tile whose own box overlaps the one asked for."""
    south, west, north, east = box
    cache = CACHE_ROOT / f"{region}_{mode}"
    if not cache.exists():
        return []
    hits = []
    for path in sorted(cache.glob("*.osm")):
        b = tile_bounds(path)
        if b is None:
            continue
        if b[0] <= north and b[2] >= south and b[1] <= east and b[3] >= west:
            hits.append(path)
    return hits


def merge_tiles(paths: list[Path], box, out_path: Path) -> Path:
    """
    One XML from many, keeping only what the box needs.

    Ways are kept whole when ANY of their nodes falls inside, and every node of
    a kept way is written even if it lies outside - a way with missing nodes
    becomes a broken geometry rather than a shorter one.
    """
    south, west, north, east = box
    nodes: dict[str, tuple[float, float]] = {}
    ways: dict[str, tuple[list[str], list[tuple[str, str]]]] = {}

    node_re = re.compile(r'<node id="(\d+)" lat="([-\d.]+)" lon="([-\d.]+)"')
    for path in paths:
        way_id = None
        refs: list[str] = []
        tags: list[tuple[str, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            m = node_re.search(line)
            if m:
                nodes.setdefault(m.group(1), (float(m.group(2)), float(m.group(3))))
                continue
            if "<way id=" in line:
                way_id = re.search(r'<way id="(\d+)"', line).group(1)
                refs, tags = [], []
            elif "<nd ref=" in line and way_id:
                refs.append(re.search(r'<nd ref="(\d+)"', line).group(1))
            elif "<tag k=" in line and way_id:
                m = re.search(r'<tag k="([^"]*)" v="([^"]*)"', line)
                if m:
                    tags.append((m.group(1), m.group(2)))
            elif "</way>" in line and way_id:
                ways.setdefault(way_id, (refs, tags))
                way_id = None

    keep_way = {}
    for way_id, (refs, tags) in ways.items():
        for ref in refs:
            pos = nodes.get(ref)
            if pos and south <= pos[0] <= north and west <= pos[1] <= east:
                keep_way[way_id] = (refs, tags)
                break
    used = {ref for refs, _ in keep_way.values() for ref in refs}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<osm version="0.6" generator="region-graph">\n')
        for node_id in used:
            pos = nodes.get(node_id)
            if pos:
                fh.write(f'  <node id="{node_id}" lat="{pos[0]}" lon="{pos[1]}"/>\n')
        for way_id, (refs, tags) in keep_way.items():
            fh.write(f'  <way id="{way_id}">\n')
            for ref in refs:
                if ref in nodes:
                    fh.write(f'    <nd ref="{ref}"/>\n')
            for key, value in tags:
                fh.write(f'    <tag k={quoteattr(key)} v={quoteattr(value)}/>\n')
            fh.write("  </way>\n")
        fh.write("</osm>\n")
    return out_path


def region_graph(lat: float, lon: float, half_size_m: float,
                 mode: str = "bike", region: str = "north") -> nx.MultiDiGraph:
    """The network around a point, stitched from the region cache."""
    box = box_around(lat, lon, half_size_m)
    paths = tiles_for(box, region, mode)
    if not paths:
        raise FileNotFoundError(
            f"no cached tiles cover {lat},{lon} +-{half_size_m:.0f} m in "
            f"{region}/{mode}; run region_download.py first")

    MERGED_DIR.mkdir(exist_ok=True)
    merged = MERGED_DIR / (f"{region}_{mode}_{lat:.4f}_{lon:.4f}_"
                           f"{half_size_m:.0f}m.osm")
    if not merged.exists():
        print(f"  stitching {len(paths)} tiles from {region}/{mode}", flush=True)
        merge_tiles(paths, box, merged)
    else:
        print(f"  using stitched network {merged.name}", flush=True)
    # Cyclists obey one-way restrictions; pedestrians do not. Same rule as
    # download_walk_graph, and getting it wrong sends the route up 8,000
    # one-way streets.
    graph = ox.graph_from_xml(merged, bidirectional=(mode == "walk"), simplify=True)
    # And project, which download_walk_graph also does. Everything downstream -
    # the street index, the placement grid, every distance in metres - assumes
    # a metric CRS. Returning the raw lat/lon graph does not fail, it silently
    # makes every measurement degrees, and the first thing measured on top of
    # it read "3.8 km from the nearest street" across the whole region.
    projected = ox.project_graph(graph)
    print(f"  network: {projected.number_of_nodes():,} nodes, "
          f"{projected.number_of_edges():,} edges, CRS {projected.graph['crs']}",
          flush=True)
    return projected


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lat", type=float, default=25.04)
    ap.add_argument("--lon", type=float, default=121.54)
    ap.add_argument("--half-size", type=float, default=7000.0)
    ap.add_argument("--mode", default="bike")
    ap.add_argument("--region", default="north", choices=sorted(REGIONS))
    args = ap.parse_args()

    box = box_around(args.lat, args.lon, args.half_size)
    paths = tiles_for(box, args.region, args.mode)
    print(f"box {box[0]:.4f},{box[1]:.4f} to {box[2]:.4f},{box[3]:.4f}")
    print(f"{len(paths)} cached tiles overlap it")
    if not paths:
        return
    graph = region_graph(args.lat, args.lon, args.half_size, args.mode, args.region)
    print(f"{graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges")


if __name__ == "__main__":
    main()
