"""
Fallback OSM downloader for environments where the Overpass API is unreachable.

`osmnx` normally talks to Overpass. Some sandboxed / firewalled environments
block every Overpass mirror but still allow the official OSM Map API at
api.openstreetmap.org. That API has two hard limits:

  * a bounding box may not exceed 0.25 square degrees, and
  * a single response may not exceed 50,000 nodes.

Central Taipei is dense enough that a 4 km x 4 km box blows past the node cap,
so this module downloads the box as a grid of small tiles, keeps only the ways
that a pedestrian may use, and writes a single minimal .osm XML file that
`osmnx.graph_from_xml()` can read.

This exists purely so the POC can run in a locked-down container. If Overpass
is reachable, `heart_route_poc.py` uses osmnx's normal code path instead.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from xml.sax.saxutils import quoteattr

import requests
from xml.etree import ElementTree as ET

OSM_MAP_API = "https://api.openstreetmap.org/api/0.6/map"

# Mirrors osmnx's built-in "walk" network filter. osmnx expresses it as an
# Overpass regex; here the same rules are applied to parsed tags directly.
# Substring matching is intentional: "motor" must also reject "motorway_link".
_EXCLUDED_HIGHWAY_SUBSTRINGS = (
    "abandoned", "bus_guideway", "construction", "cycleway", "motor",
    "planned", "platform", "proposed", "raceway", "razed",
)


def _way_is_walkable(tags: dict[str, str]) -> bool:
    """Return True if a pedestrian may reasonably walk along this OSM way."""
    highway = tags.get("highway")
    if not highway or highway == "no":
        return False
    if any(bad in highway for bad in _EXCLUDED_HIGHWAY_SUBSTRINGS):
        return False
    if tags.get("area") == "yes":
        return False
    if tags.get("foot") == "no":
        return False
    if tags.get("service") == "private":
        return False
    if tags.get("access") == "private":
        return False
    return True


def _tile_bboxes(
    north: float, south: float, east: float, west: float, step_deg: float
) -> list[tuple[float, float, float, float]]:
    """Split a lat/lon box into a grid of tiles, each small enough for the API."""
    n_lat = max(1, math.ceil((north - south) / step_deg))
    n_lon = max(1, math.ceil((east - west) / step_deg))
    d_lat = (north - south) / n_lat
    d_lon = (east - west) / n_lon
    tiles = []
    for i in range(n_lat):
        for j in range(n_lon):
            s = south + i * d_lat
            w = west + j * d_lon
            tiles.append((w, s, w + d_lon, s + d_lat))  # OSM API order: W,S,E,N
    return tiles


def _fetch_tile(bbox: tuple[float, float, float, float], retries: int = 4) -> bytes:
    """GET one tile from the OSM Map API, retrying with exponential backoff."""
    url = f"{OSM_MAP_API}?bbox={bbox[0]:.6f},{bbox[1]:.6f},{bbox[2]:.6f},{bbox[3]:.6f}"
    delay = 2.0
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:  # noqa: BLE001 - any transport error is retryable
            if attempt == retries - 1:
                raise
            print(f"    tile fetch failed ({exc}); retrying in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def _parse_tile(raw: bytes, nodes: dict, ways: dict) -> None:
    """Merge one tile's walkable ways (and the nodes they use) into the accumulators."""
    root = ET.fromstring(raw)

    # Every node in the tile, including ones outside the bbox that a returned
    # way references - the Map API guarantees those are present.
    tile_nodes = {}
    for node in root.findall("node"):
        tile_nodes[node.get("id")] = (node.get("lat"), node.get("lon"))

    for way in root.findall("way"):
        way_id = way.get("id")
        if way_id in ways:
            continue  # already collected from an adjacent tile
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        if not _way_is_walkable(tags):
            continue
        refs = [nd.get("ref") for nd in way.findall("nd")]
        ways[way_id] = (refs, tags)
        for ref in refs:
            if ref in tile_nodes:
                nodes[ref] = tile_nodes[ref]


def download_walk_xml(
    center_lat: float,
    center_lon: float,
    half_size_m: float,
    out_path: Path,
    step_deg: float = 0.008,
) -> Path:
    """
    Download the walkable street network around a point and write it as OSM XML.

    `half_size_m` is half the side length of the square box, in metres, so the
    covered area is (2 * half_size_m)^2.
    """
    # Metres -> degrees. Longitude degrees shrink with cos(latitude).
    d_lat = half_size_m / 111_320.0
    d_lon = half_size_m / (111_320.0 * math.cos(math.radians(center_lat)))
    north, south = center_lat + d_lat, center_lat - d_lat
    east, west = center_lon + d_lon, center_lon - d_lon

    tiles = _tile_bboxes(north, south, east, west, step_deg)
    print(f"  fetching {len(tiles)} tiles from the OSM Map API "
          f"(box {2 * half_size_m / 1000:.1f} km x {2 * half_size_m / 1000:.1f} km)")

    nodes: dict[str, tuple[str, str]] = {}
    ways: dict[str, tuple[list[str], dict[str, str]]] = {}
    for idx, bbox in enumerate(tiles, start=1):
        _parse_tile(_fetch_tile(bbox), nodes, ways)
        print(f"    tile {idx}/{len(tiles)}: {len(ways)} walkable ways, "
              f"{len(nodes)} nodes so far")

    # Drop nodes no retained way references, then write the minimal XML file.
    used = {ref for refs, _ in ways.values() for ref in refs}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write('<osm version="0.6" generator="heart-route-poc-tiler">\n')
        for node_id, (lat, lon) in nodes.items():
            if node_id in used:
                fh.write(f'  <node id="{node_id}" lat="{lat}" lon="{lon}"/>\n')
        for way_id, (refs, tags) in ways.items():
            fh.write(f'  <way id="{way_id}">\n')
            for ref in refs:
                fh.write(f'    <nd ref="{ref}"/>\n')
            for key, value in tags.items():
                fh.write(f'    <tag k={quoteattr(key)} v={quoteattr(value)}/>\n')
            fh.write("  </way>\n")
        fh.write("</osm>\n")

    print(f"  wrote {out_path} ({len(ways)} ways, {len(used)} nodes)")
    return out_path
