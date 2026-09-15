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
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA = "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd"

# Devices cap how many points a ROUTE may carry, far below what a track may
# hold. The track keeps every point; the route is simplified to the corners.
ROUTE_TOLERANCE_M = 8.0
ROUTE_MAX_POINTS = 500


def _to_latlon(xy: np.ndarray, crs: str) -> np.ndarray:
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(
        xy[:, 0], xy[:, 1])
    return np.column_stack([lat, lon])


def _simplify(xy: np.ndarray, tolerance: float) -> np.ndarray:
    """
    Douglas-Peucker: drop points that lie within `tolerance` of the line their
    neighbours already describe.

    Corners are what a rider navigates by, and they are exactly the points this
    keeps. Straight runs down an avenue are where the redundant points are.
    """
    keep = np.zeros(len(xy), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(xy) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        seg = xy[lo:hi + 1]
        d = xy[hi] - xy[lo]
        length = float(np.hypot(*d))
        if length == 0:
            dist = np.hypot(*(seg - xy[lo]).T)
        else:
            u = d / length
            dist = np.abs(u[0] * (seg[:, 1] - xy[lo, 1])
                          - u[1] * (seg[:, 0] - xy[lo, 0]))
        k = int(np.argmax(dist))
        if dist[k] > tolerance:
            keep[lo + k] = True
            stack.extend([(lo, lo + k), (lo + k, hi)])
    return xy[keep]


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
    lats, lons = points[:, 0], points[:, 1]
    bounds = (f'    <bounds minlat="{lats.min():.7f}" minlon="{lons.min():.7f}" '
              f'maxlat="{lats.max():.7f}" maxlon="{lons.max():.7f}"/>')
    track = "\n".join(
        f'      <trkpt lat="{lat:.7f}" lon="{lon:.7f}"></trkpt>'
        for lat, lon in points
    )

    # The same line again as a route, simplified to what a device will accept.
    xy = np.asarray(route_xy, dtype=float)
    tolerance = ROUTE_TOLERANCE_M
    simple = _simplify(xy, tolerance)
    while len(simple) > ROUTE_MAX_POINTS and tolerance < 200.0:
        tolerance *= 1.6
        simple = _simplify(xy, tolerance)
    rte_points = _to_latlon(simple, crs)
    if close_loop and not np.allclose(rte_points[0], rte_points[-1]):
        rte_points = np.vstack([rte_points, rte_points[:1]])
    route = "\n".join(
        f'    <rtept lat="{lat:.7f}" lon="{lon:.7f}"></rtept>'
        for lat, lon in rte_points
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<gpx version="1.1" creator="shape-route-poc" xmlns="{GPX_NS}" '
        f'xmlns:xsi="{XSI_NS}" xsi:schemaLocation="{SCHEMA}">\n'
        f"  <metadata>\n"
        f"    <name>{escape(name)}</name>\n"
        f"    <desc>{escape(description)}</desc>\n"
        f"    <time>{stamp}</time>\n"
        f"{bounds}\n"
        f"  </metadata>\n"
        f"  <rte>\n"
        f"    <name>{escape(name)}</name>\n"
        f"    <type>cycling</type>\n"
        f"{route}\n"
        f"  </rte>\n"
        f"  <trk>\n"
        f"    <name>{escape(name)}</name>\n"
        f"    <type>cycling</type>\n"
        f"    <trkseg>\n{track}\n    </trkseg>\n"
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
