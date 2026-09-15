"""
The street scale, measured where the route will be drawn.

MODES carries one street_scale_m per mode - 280 m for cycling - fitted in
Taipei and applied to the whole island. POC 26 tested that across seven cities
and it does not hold. The directional street scale (the median distance to the
nearest street heading a chosen way, averaged over twelve directions) spans
141 m in Banqiao to 223 m in Keelung, and it predicts what the pipeline
produces there: shape distance r = +0.74, detour r = +0.60.

Keelung is the case that matters. Asked for a 10 km heart it returned 15.0 km
at a shape distance of 0.266 - half again as long as requested, and nowhere
near recognisable - because 280 m anchors demand a density of streets that
Keelung does not have. The constant does not merely scatter across cities; it
asks a sparse city for detail it cannot draw.

So street_scale becomes a property of the place. A place's scale is the
national constant times its directional scale over Taipei's, both measured the
same way in the same mode, which keeps Taipei exactly where nine POCs of
measurement put it and moves everywhere else relative to it.

Cycling only. Every measurement behind this is on the bike network, and the
walking constant rests on nine POCs of its own; scaling it by a ratio measured
on a different graph would be the kind of borrowed transfer this project keeps
having to take back out.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from routeshape import paths

STEP_M = 15.0
DIR_TOLERANCE_DEG = 10.0
SAMPLES = 3000
NEAR_TOWN_M = 250.0

# Taipei, measured by POC 26 with exactly the function below: 142 m on the bike
# network at 25.0400,121.5400. The denominator of every ratio.
REFERENCE_DIRECTIONAL_M = {"bike": 142.0}

CACHE_PATH = paths.STREET_SCALE_CACHE
# The service is a ThreadingHTTPServer, so two requests for two places can be
# in remember() at once. Read-modify-write on a shared file without this loses
# entries, and worse: a read landing inside another thread's truncation window
# returns empty, the ValueError is swallowed as "no cache", and the file is
# rewritten with one entry - silently discarding every city measured so far.
_LOCK = threading.Lock()

# Measured at this half-size and no other. The reference 142 m for Taipei was
# taken over a 5 km box; measuring a different place over whatever box the
# first caller's distance happened to need would compare two different things
# and then cache the answer permanently.
MEASURE_HALF_M = 5000.0
# How far a cached measurement carries. Street density changes over a few km,
# and re-measuring costs a full pass over the graph.
CACHE_PRECISION = 2          # decimal places of lat/lon, ~1.1 km


def directional_scale(graph, seed: int = 0) -> float | None:
    """Median distance to the nearest street heading a chosen way, over 12 ways.

    Not the distance to the nearest street of any kind. That is 19 m in Taipei
    against 142 m here, because a route has to follow a heading and most
    streets do not run the way it needs to go. The plain figure also spans 3.5x
    across cities where this one spans 1.6x, so it exaggerates differences that
    the fitted routes do not show.
    """
    X = {n: (d["x"], d["y"]) for n, d in graph.nodes(data=True)}
    pts, brg = [], []
    for u, v, _ in graph.edges(data=True):
        (x1, y1), (x2, y2) = X[u], X[v]
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length <= 0:
            continue
        k = max(2, int(length / STEP_M) + 1)
        t = np.linspace(0, 1, k)
        pts.append(np.column_stack([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t]))
        brg.append(np.full(k, np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180.0))
    if not pts:
        return None
    P = np.vstack(pts)
    B = np.concatenate(brg)
    base = cKDTree(P)
    rng = np.random.default_rng(seed)
    lo, hi = P.min(axis=0), P.max(axis=0)
    S = rng.uniform(lo, hi, size=(SAMPLES, 2))
    # Only where there is a town. Otherwise the answer is the sea and the
    # mountains, which no route crosses.
    S = S[base.query(S)[0] <= NEAR_TOWN_M]
    if len(S) < 200:
        return None
    per = []
    for th in range(0, 180, 15):
        sel = np.abs((B - th + 90) % 180 - 90) <= DIR_TOLERANCE_DEG
        if sel.sum() >= 100:
            per.append(float(np.median(cKDTree(P[sel]).query(S)[0])))
    return float(np.mean(per)) if per else None


def _load() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except (ValueError, OSError):
            return {}
    return {}


def _key(lat: float, lon: float, mode: str) -> str:
    return f"{mode}:{lat:.{CACHE_PRECISION}f},{lon:.{CACHE_PRECISION}f}"


_MISSING = object()


def cached_directional(lat: float, lon: float, mode: str, default=None):
    """The stored measurement. `default` distinguishes "not measured" from
    "measured and came back None", which the plain None return cannot."""
    return _load().get(_key(lat, lon, mode), default)


def is_measured(lat: float, lon: float, mode: str) -> bool:
    return cached_directional(lat, lon, mode, _MISSING) is not _MISSING


def remember(lat: float, lon: float, mode: str, value: float | None) -> None:
    """Record a measurement, including a failed one.

    None is stored as null rather than skipped: a place where the measurement
    cannot be taken would otherwise miss the cache forever and pay a full
    twelve-direction pass over the graph on every single request.
    """
    with _LOCK:
        data = _load()
        data[_key(lat, lon, mode)] = value
        try:
            # Write a temporary file and rename it over the target. rename is
            # atomic, so a concurrent reader sees either the old file or the
            # new one, never a half-truncated one.
            fd, tmp = tempfile.mkstemp(dir=str(CACHE_PATH.parent),
                                       prefix="._scale", suffix=".json")
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, indent=2, sort_keys=True)
            os.replace(tmp, CACHE_PATH)
        except OSError:
            pass      # a cache that cannot be written is slow, not wrong


def scale_for(lat: float, lon: float, mode: str, base_scale_m: float,
              graph=None) -> float:
    """This place's street scale, or the national constant when unmeasured.

    Falls back rather than blocking: a place with no measurement yet gets the
    constant, which is what it would have got anyway. Pass `graph` to measure
    and remember on the spot.
    """
    reference = REFERENCE_DIRECTIONAL_M.get(mode)
    if reference is None:
        return base_scale_m
    value = cached_directional(lat, lon, mode, _MISSING)
    if value is _MISSING:
        if graph is None:
            return base_scale_m
        value = directional_scale(graph)
        remember(lat, lon, mode, value)
    if value is None:
        return base_scale_m
    return base_scale_m * value / reference
