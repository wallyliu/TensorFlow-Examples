"""Where this project keeps things on disk, independent of where the code sits.

Every data path used to be written as `Path(__file__).with_name(...)`, which
was correct only while all 71 modules lived in one directory. Moving them into
a package silently repointed the map cache at routeshape/region/_region_cache,
and the service started re-downloading a network it already had - no error, no
warning, just five minutes of tiles. Anchoring on the project root instead
means a module can move without taking its data with it.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

REGION_CACHE = PROJECT_ROOT / "_region_cache"     # downloaded map tiles
REGION_MERGED = PROJECT_ROOT / "_region_merged"   # stitched networks
NETWORK_CACHE = PROJECT_ROOT                      # per-point .graphml / .osm
STREET_SCALE_CACHE = PROJECT_ROOT / "_street_scale_cache.json"
RESULTS = PROJECT_ROOT / "results"                # figures and measurements
GPX = PROJECT_ROOT / "gpx"
