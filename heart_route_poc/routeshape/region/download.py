"""
Download a whole region's rideable network, in pieces, so it survives being
interrupted.

The per-tile downloader in `osm_api_fallback` covers a square around a point
with a fixed 0.008-degree grid. That grid was sized for the densest part of
Taipei, and using it over a region wastes most of its requests: a tile over
farmland or water costs the same round trip as one over Zhongshan District and
returns almost nothing. Covering the five northern counties that way needs
roughly eleven thousand requests.

Two changes make a region practical.

ADAPTIVE TILES. Start at a coarse step and split a tile into four only when the
API refuses it for holding too much data. Dense districts end up finely divided
and the Pacific Ocean stays one tile, so the request count follows the data
rather than the area.

RESUMABLE. Every accepted tile is written to its own file under a cache
directory before moving on. A container restart, a network failure or a
deliberate stop costs only the tile in flight - rerun the same command and it
picks up where it stopped. This matters because a region takes hours and this
project has already lost two multi-hour jobs to restarts.

Run:  python region_download.py --region north --mode bike
      python region_download.py --region north --mode bike --status
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from xml.sax.saxutils import quoteattr

import requests

from routeshape.region.osm_api import FILTERS, OSM_MAP_API, _parse_tile
from routeshape import paths

CACHE_ROOT = paths.REGION_CACHE

# north = 北北基桃宜: Taipei, New Taipei, Keelung, Taoyuan, Yilan.
# A non-overlapping partition of the main island, so no square is ever
# downloaded twice into two different caches. Between them they span
# 21.85-25.30 N, which is Taiwan from 鵝鑾鼻 to 富貴角.
#
# "north" keeps the bounds it was downloaded with rather than the tidier ones
# this partition would give it: 515 tiles are already on disk under those
# bounds and renaming them would throw the lot away. Its western edge at 121.00
# leaves 新竹 outside, which is what "northwest" exists to cover.
REGIONS = {
    "north": {"south": 24.60, "north": 25.30, "west": 121.00, "east": 122.05,
              "label": "北北基桃宜"},
    "northwest": {"south": 24.60, "north": 25.30, "west": 120.50, "east": 121.00,
                  "label": "竹苗北"},
    "central": {"south": 23.30, "north": 24.60, "west": 120.00, "east": 122.05,
                "label": "中彰投苗雲花北"},
    "south": {"south": 21.85, "north": 23.30, "west": 120.00, "east": 121.70,
              "label": "嘉南高屏東"},
    "taipei": {"south": 24.95, "north": 25.21, "west": 121.45, "east": 121.68,
               "label": "台北盆地"},
}

# Which regions make up the island, in the order a whole-country download
# should take them. "taipei" is excluded: it is a subset of "north", kept only
# because the early POCs used it.
ISLAND = ("north", "northwest", "central", "south")


def region_for(lat: float, lon: float) -> str | None:
    """The island region containing a point, or None if it is off the map.

    Needed because everything downstream defaulted to "north". With one region
    that was merely redundant; with four it means a request for Tainan quietly
    reads the Taipei cache, finds nothing, and reports the map as missing.
    """
    for name in ISLAND:
        b = REGIONS[name]
        if b["south"] <= lat <= b["north"] and b["west"] <= lon <= b["east"]:
            return name
    return None

START_STEP = 0.08          # coarse enough that empty country costs one request
MIN_STEP = 0.005           # finer than this and the densest blocks still fail
REQUEST_PAUSE = 1.0        # be a polite client of a volunteer-run API


def tile_key(bbox) -> str:
    return f"{bbox[1]:.4f}_{bbox[0]:.4f}_{bbox[3]:.4f}_{bbox[2]:.4f}"


def fetch(bbox, timeout: int = 180):
    """
    Return the tile's bytes, or None when the API says the box holds too much.

    Only 400 means "too big, split it". 509 is the bandwidth limiter and 429 is
    the rate limiter - both mean "come back later", and splitting on them makes
    it worse: one refusal becomes four requests, then sixteen, and the ground
    underneath is abandoned at MIN_STEP having never been fetched. They wait
    instead, and so do 5xx, which used to be fatal because HTTPError was
    re-raised while socket errors retried.
    """
    url = (f"{OSM_MAP_API}?bbox={bbox[0]:.5f},{bbox[1]:.5f},"
           f"{bbox[2]:.5f},{bbox[3]:.5f}")
    delay = 3.0
    for attempt in range(5):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 400:
                return None                       # too big: split it
            if resp.status_code in (429, 509) or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.content
        except Exception as exc:       # noqa: BLE001 - everything else retries
            if attempt == 4:
                raise
            print(f"      retry in {delay:.0f}s ({exc})", flush=True)
            time.sleep(delay)
            delay *= 2
    return None


def write_tile(path: Path, nodes: dict, ways: dict) -> None:
    used = {ref for refs, _ in ways.values() for ref in refs}
    with path.open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" '
                 'generator="region-download">\n')
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


def cover(bounds: dict, step: float) -> list:
    """The coarse grid the adaptive pass starts from."""
    tiles = []
    lat = bounds["south"]
    while lat < bounds["north"]:
        lon = bounds["west"]
        while lon < bounds["east"]:
            tiles.append((lon, lat, min(lon + step, bounds["east"]),
                          min(lat + step, bounds["north"])))
            lon += step
        lat += step
    return tiles


def run(region: str, mode: str, near: tuple[float, float] | None = None) -> None:
    bounds = REGIONS[region]
    keep_way = FILTERS[mode]
    cache = CACHE_ROOT / f"{region}_{mode}"
    cache.mkdir(parents=True, exist_ok=True)
    state_path = cache / "_state.json"
    done = set(json.loads(state_path.read_text())) if state_path.exists() else set()
    # Tiles already known to be too big. Without this every restart re-issues
    # the request for each split ancestor just to be told 400 again, and those
    # are the slowest requests there are - the server evaluates the whole box
    # before rejecting it. This container gets recycled often, so restarts are
    # the common case, not the rare one.
    splits_path = cache / "_splits.json"
    known_split = (set(json.loads(splits_path.read_text()))
                   if splits_path.exists() else set())

    queue = cover(bounds, START_STEP)
    if near:
        # Row-major from the south-west corner is an arbitrary order that
        # happens to leave the cities late: central Taipei is coarse tile 76 of
        # 126. Sorting by distance from a point of interest costs nothing and
        # makes the region usable around that point first.
        queue.sort(key=lambda b: (((b[1] + b[3]) / 2 - near[0]) ** 2
                                  + ((b[0] + b[2]) / 2 - near[1]) ** 2))
    print(f"{bounds['label']} ({region}), {mode}: starting from "
          f"{len(queue)} coarse tiles, {len(done)} already cached"
          + (f", nearest first around {near[0]},{near[1]}" if near else ""),
          flush=True)

    fetched = split = 0
    t0 = time.time()
    while queue:
        bbox = queue.pop(0)
        key = tile_key(bbox)
        if key in done:
            continue
        raw = None if key in known_split else fetch(bbox)
        if raw is None:
            # Two steps, not one. A tile clipped at the region edge is not
            # square, and using the longitude half-width for latitude as well
            # either leaves a band of it unfetched or overshoots the region.
            # On the real tile (121.61, 25.03)-(121.68, 25.11) the single-step
            # version missed 1.1 km of latitude across the whole width.
            lon_step = (bbox[2] - bbox[0]) / 2
            lat_step = (bbox[3] - bbox[1]) / 2
            if min(lon_step, lat_step) < MIN_STEP:
                print(f"    giving up on {key}: still too big at "
                      f"{min(lon_step, lat_step):.4f} deg", flush=True)
                done.add(key)
                state_path.write_text(json.dumps(sorted(done)))
                continue
            if key not in known_split:
                split += 1
                known_split.add(key)
                splits_path.write_text(json.dumps(sorted(known_split)))
            # Depth first: the children go to the FRONT. Appending them sent a
            # dense area to the back of the queue once per subdivision level,
            # and the densest areas subdivide the most - Taipei was demoted
            # behind the whole region three times over, which is why the city
            # that matters most arrived last. Front-loading also keeps the
            # queue short and leaves the finished part contiguous, so coverage
            # becomes usable somewhere instead of thin everywhere.
            children = [(bbox[0] + dx * lon_step, bbox[1] + dy * lat_step,
                         bbox[0] + (dx + 1) * lon_step,
                         bbox[1] + (dy + 1) * lat_step)
                        for dx in (0, 1) for dy in (0, 1)]
            queue[:0] = children
            continue

        nodes: dict = {}
        ways: dict = {}
        _parse_tile(raw, nodes, ways, keep_way)
        if ways:
            write_tile(cache / f"{key}.osm", nodes, ways)
        done.add(key)
        state_path.write_text(json.dumps(sorted(done)))
        fetched += 1
        rate = fetched / max(time.time() - t0, 1e-9) * 60
        print(f"    [{fetched:4d} kept, {split:3d} split, {len(queue):4d} queued] "
              f"{key}: {len(ways)} ways  ({rate:.1f} tiles/min)", flush=True)
        time.sleep(REQUEST_PAUSE)

    print(f"\ndone: {fetched} tiles kept, {split} splits, "
          f"{time.time() - t0:.0f}s", flush=True)


def status(region: str, mode: str) -> None:
    cache = CACHE_ROOT / f"{region}_{mode}"
    files = sorted(cache.glob("*.osm")) if cache.exists() else []
    size = sum(f.stat().st_size for f in files)
    print(f"{region}/{mode}: {len(files)} tiles cached, {size / 1e6:.1f} MB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default="north", choices=sorted(REGIONS))
    ap.add_argument("--mode", default="bike", choices=sorted(FILTERS))
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--near", help="lat,lon to fetch outward from, e.g. 25.04,121.54")
    args = ap.parse_args()
    if args.status:
        status(args.region, args.mode)
    else:
        near = None
        if args.near:
            lat, lon = (float(v) for v in args.near.split(","))
            near = (lat, lon)
        run(args.region, args.mode, near)


if __name__ == "__main__":
    main()
