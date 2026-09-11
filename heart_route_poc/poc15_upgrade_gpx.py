"""
Re-emit every exported route in a form a bike computer will take.

The first export wrote a bare GPX 1.1 track. Three things were missing for the
devices these files exist to be ridden on: the schema declaration some importers
insist on, a <bounds> so a map can frame the route without reading every point,
and a <rte> block - devices that navigate routes rather than replay tracks cap
route points far below what a track may carry, so the route is the same line
simplified to its corners (Douglas-Peucker, 8 m, widened until it fits 500).

The geometry is unchanged: the track still carries every original point. This
reads the existing files rather than refitting, so nothing can drift.

Run:  python poc15_upgrade_gpx.py
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from pyproj import Transformer

from route_export import to_gpx

GPX_DIR = Path(__file__).with_name("gpx")
NS = {"g": "http://www.topografix.com/GPX/1/1"}
CRS = "EPSG:32651"


def main() -> None:
    to_utm = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    print(f"{'file':<28}{'trkpt':>7}{'rtept':>7}{'KB':>7}")
    for path in sorted(GPX_DIR.glob("*.gpx")):
        root = ET.parse(path).getroot()
        pts = root.findall(".//g:trkpt", NS)
        lat = np.array([float(p.get("lat")) for p in pts])
        lon = np.array([float(p.get("lon")) for p in pts])
        x, y = to_utm.transform(lon, lat)
        name = root.findtext("g:metadata/g:name", default=path.stem, namespaces=NS)
        desc = root.findtext("g:metadata/g:desc", default="", namespaces=NS)

        gpx = to_gpx(np.column_stack([x, y]), CRS, name, desc)
        path.write_text(gpx, encoding="utf-8")

        check = ET.fromstring(gpx)
        print(f"{path.name:<28}{len(check.findall('.//g:trkpt', NS)):>7}"
              f"{len(check.findall('.//g:rtept', NS)):>7}"
              f"{path.stat().st_size / 1024:>7.0f}")


if __name__ == "__main__":
    main()
