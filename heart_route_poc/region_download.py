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

from osm_api_fallback import FILTERS, OSM_MAP_API, _parse_tile

CACHE_ROOT = Path(__file__).with_name("_region_cache")

# north = 北北基桃宜: Taipei, New Taipei, Keelung, Taoyuan, Yilan.
REGIONS = {
    "north": {"south": 24.60, "north": 25.30, "west": 121.00, "east": 122.05,
              "label": "北北基桃宜"},
    "taipei": {"south": 24.95, "north": 25.21, "west": 121.45, "east": 121.68,
               "label": "台北盆地"},
}

START_STEP = 0.08          # coarse enough that empty country costs one request
MIN_STEP = 0.005           # finer than this and the densest blocks still fail
REQUEST_PAUSE = 1.0        # be a polite client of a volunteer-run API


def tile_key(bbox) -> str:
    return f"{bbox[1]:.4f}_{bbox[0]:.4f}_{bbox[3]:.4f}_{bbox[2]:.4f}"


def fetch(bbox, timeout: int = 180):
    """Return the tile's bytes, or None when the API says it holds too much."""
    url = (f"{OSM_MAP_API}?bbox={bbox[0]:.5f},{bbox[1]:.5f},"
           f"{bbox[2]:.5f},{bbox[3]:.5f}")
    delay = 3.0
    for attempt in range(4):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code in (400, 509):
                return None            # too big, or bandwidth-limited: split it
            resp.raise_for_status()
            return resp.content
        except requests.HTTPError:
            raise
        except Exception as exc:       # noqa: BLE001 - transport errors retry
            if attempt == 3:
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


def run(region: str, mode: str) -> None:
    bounds = REGIONS[region]
    keep_way = FILTERS[mode]
    cache = CACHE_ROOT / f"{region}_{mode}"
    cache.mkdir(parents=True, exist_ok=True)
    state_path = cache / "_state.json"
    done = set(json.loads(state_path.read_text())) if state_path.exists() else set()

    queue = cover(bounds, START_STEP)
    print(f"{bounds['label']} ({region}), {mode}: starting from "
          f"{len(queue)} coarse tiles, {len(done)} already cached", flush=True)

    fetched = split = 0
    t0 = time.time()
    while queue:
        bbox = queue.pop(0)
        key = tile_key(bbox)
        if key in done:
            continue
        raw = fetch(bbox)
        if raw is None:
            step = (bbox[2] - bbox[0]) / 2
            if step < MIN_STEP:
                print(f"    giving up on {key}: still too big at {step:.4f} deg",
                      flush=True)
                done.add(key)
                continue
            split += 1
            for dx in (0, 1):
                for dy in (0, 1):
                    queue.append((bbox[0] + dx * step, bbox[1] + dy * step,
                                  bbox[0] + (dx + 1) * step,
                                  bbox[1] + (dy + 1) * step))
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
    args = ap.parse_args()
    if args.status:
        status(args.region, args.mode)
    else:
        run(args.region, args.mode)


if __name__ == "__main__":
    main()
