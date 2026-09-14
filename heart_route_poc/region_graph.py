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
from xml.sax.saxutils import quoteattr, unescape

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


class RegionNotCovered(FileNotFoundError):
    """
    The cache reaches this box but does not fill it.

    A subclass of FileNotFoundError so every caller that already falls back on
    a missing region falls back on a half-present one too. That distinction is
    the whole point: overlapping ONE tile is not coverage, and treating it as
    coverage is how the service came to serve central Taipei as a 153-node
    graph - against 42,146 for the same box downloaded directly - and log it as
    a success.
    """


def coverage(box, tiles: list[Path], cells: int = 40) -> float:
    """
    What fraction of the box some cached tile actually contains.

    Sampled on a grid rather than computed as a union of rectangles: the tiles
    overlap and subdivide at four different sizes, so the exact union is
    fiddly and the answer only has to be good enough to tell "covered" from
    "one tile clipping the corner".
    """
    south, west, north, east = box
    bounds = [b for b in (tile_bounds(p) for p in tiles) if b]
    if not bounds:
        return 0.0
    lats = [south + (north - south) * (i + 0.5) / cells for i in range(cells)]
    lons = [west + (east - west) * (i + 0.5) / cells for i in range(cells)]
    inside = 0
    for la in lats:
        for lo in lons:
            if any(b[0] <= la <= b[2] and b[1] <= lo <= b[3] for b in bounds):
                inside += 1
    return inside / (cells * cells)


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
                # quoteattr emits SINGLE quotes when the value contains a
                # double quote, so a regex fixed on double quotes drops those
                # tags silently. Both forms, and unescape once so re-stitching
                # does not turn & into &amp;amp;.
                m = re.search(r'<tag k=(["\'])(.*?)\1 v=(["\'])(.*?)\3', line)
                if m:
                    tags.append((unescape(m.group(2)), unescape(m.group(4))))
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


MIN_COVERAGE = 0.98


def region_graph(lat: float, lon: float, half_size_m: float,
                 mode: str = "bike", region: str = "north",
                 min_coverage: float = MIN_COVERAGE) -> nx.MultiDiGraph:
    """The network around a point, stitched from the region cache."""
    box = box_around(lat, lon, half_size_m)
    paths = tiles_for(box, region, mode)
    if not paths:
        raise RegionNotCovered(
            f"no cached tiles cover {lat},{lon} +-{half_size_m:.0f} m in "
            f"{region}/{mode}; run region_download.py first")
    covered = coverage(box, paths)
    if covered < min_coverage:
        raise RegionNotCovered(
            f"{region}/{mode} covers only {covered:.0%} of the box at "
            f"{lat},{lon} +-{half_size_m:.0f} m; the download has not finished "
            f"here")

    MERGED_DIR.mkdir(exist_ok=True)
    merged = MERGED_DIR / (f"{region}_{mode}_{lat:.4f}_{lon:.4f}_"
                           f"{half_size_m:.0f}m.osm")
    # Restitch when any source tile is newer than the stitch. Without this a
    # stitch made while the download was still running is frozen for good, and
    # the cache filled up with exactly that: central Taipei at 335 KB beside
    # rural Yilan at 3.8 MB.
    newest = max((p.stat().st_mtime for p in paths), default=0.0)
    if not merged.exists() or merged.stat().st_mtime < newest:
        print(f"  stitching {len(paths)} tiles from {region}/{mode} "
              f"({covered:.0%} coverage)", flush=True)
        merge_tiles(paths, box, merged)
    else:
        print(f"  using stitched network {merged.name}", flush=True)
    # Cyclists obey one-way restrictions; pedestrians do not. Same rule as
    # download_walk_graph, and getting it wrong sends the route up 8,000
    # one-way streets.
    try:
        graph = ox.graph_from_xml(merged, bidirectional=(mode == "walk"),
                                  simplify=True)
    except Exception as exc:      # noqa: BLE001 - osmnx raises its own type here
        # An empty or unusable stitch is a gap in the cache, not a crash. Remove
        # the file too: leaving it means the mtime check above thinks the point
        # is cached and it stays broken for good.
        merged.unlink(missing_ok=True)
        raise RegionNotCovered(
            f"{region}/{mode} has tiles around {lat},{lon} but they yield no "
            f"usable network ({type(exc).__name__})") from exc
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
