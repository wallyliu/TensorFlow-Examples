"""
Turn a fitted route into a file someone can actually ride.

Ten POCs produced matplotlib PNGs. Nobody could take any of it outside, which
matters more than it sounds: every substantive correction in this project has
come from contact with something external - three rater rounds, and the user
pointing out the target mode was wrong. A GPX file is the cheapest possible way
to let the outside world push back.

GPX 1.1 because every device reads it: Garmin, Wahoo, Strava, Komoot, Ride with
GPS, and both phone OSes. No elevation is written - this pipeline has never had
elevation data, and inventing zeros would make devices draw a flat profile as if
it were measured.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from pyproj import Transformer

GPX_NS = "http://www.topografix.com/GPX/1/1"


def _to_latlon(xy: np.ndarray, crs: str) -> np.ndarray:
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(
        xy[:, 0], xy[:, 1])
    return np.column_stack([lat, lon])


def to_gpx(
    route_xy: np.ndarray,
    crs: str,
    name: str,
    description: str = "",
    close_loop: bool = True,
) -> str:
    """
    Serialise a route as GPX 1.1.

    `close_loop` repeats the first point at the end. These routes are closed
    loops, and without the repeat a device shows a gap between the last point
    and the first and reports a distance short by that segment.
    """
    points = _to_latlon(np.asarray(route_xy, dtype=float), crs)
    if close_loop and not np.allclose(points[0], points[-1]):
        points = np.vstack([points, points[:1]])

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = "\n".join(
        f'      <trkpt lat="{lat:.7f}" lon="{lon:.7f}"></trkpt>'
        for lat, lon in points
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<gpx version="1.1" creator="shape-route-poc" xmlns="{GPX_NS}">\n'
        f"  <metadata>\n"
        f"    <name>{escape(name)}</name>\n"
        f"    <desc>{escape(description)}</desc>\n"
        f"    <time>{stamp}</time>\n"
        f"  </metadata>\n"
        f"  <trk>\n"
        f"    <name>{escape(name)}</name>\n"
        f"    <type>cycling</type>\n"
        f"    <trkseg>\n{body}\n    </trkseg>\n"
        f"  </trk>\n"
        f"</gpx>\n"
    )


def write_gpx(result: dict, crs: str, path: Path, name: str, shape: str,
              mode: str = "bike") -> Path:
    """Write a POC 6/10 fit result straight to a .gpx file."""
    m = result["metrics"]
    description = (
        f"{shape} · {m['route_km']:.1f} km · {mode} · "
        f"shape distance {result['distance']:.3f} · "
        f"{m['backtracked_edges']} repeated segments"
    )
    path.write_text(to_gpx(result["route_xy"], crs, name, description))
    return path
