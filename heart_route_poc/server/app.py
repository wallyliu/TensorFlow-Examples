"""
A small HTTP service that turns a shape and a distance into a route file.

Everything the pipeline does has been reachable only by running Python in a
terminal. This is the same pipeline behind three endpoints, so a page can ask
for a route and get a .gpx back.

Standard library only - no framework to install. That is a deliberate choice
for something a person has to be able to run in one command, and it still holds
for the reason it always did: the web layer is nowhere near the bottleneck.

WHAT THE BOTTLENECK ACTUALLY COSTS, measured at the 30 km default in Taipei:
8 s for the gear, 19 s for the plane, 53 s for the fish. This docstring said
"2-4 seconds" for a long time after that stopped being true - that was measured
when the default was 10 km and a shape was forty contour points. Distance buys
contour points, contour points buy candidate sets, and the Viterbi is quadratic
in the candidates per point.

Part of the spread was a bug rather than the work: the search stopped early at
a fixed recognition rate of 0.97, which a MEASURED rate cannot reach, so every
shape used all six placements. `recognition.as_good_as_rated` replaced it and
took the 25 km gear from 20 s to 6.

What actually costs time is the street network. Downloading one city takes
minutes and it is the same network for every request in that city, so it is
loaded once per (place, mode) and kept. The first request after startup pays
for it; the rest do not. `--warm` pays it up front instead.

Run:  python server/app.py            # http://127.0.0.1:8000
      python server/app.py --warm     # load the Taipei bike network first
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from urllib.parse import parse_qs, urlparse
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import routeshape.shapes.multi_contour as mc                                      # noqa: E402
import routeshape.feasibility as rf                                   # noqa: E402
from routeshape.network import download_walk_graph                  # noqa: E402
from routeshape.matching import NoRouteFoundError                   # noqa: E402
from routeshape.placement import (GRID_STEP_M, MIN_SEPARATION_M,     # noqa: E402
                              NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON,
                              build_center_grid, build_street_index,
                              select_candidates)
from routeshape.placement import place_shape                          # noqa: E402
from routeshape.search import ROTATIONS_DEG, coarse_scan, refine       # noqa: E402
from routeshape.region.graph import (MIN_COVERAGE, box_around, coverage,        # noqa: E402
                          fetched_bounds, region_graph,
                          regions_overlapping, tiles_for)
from routeshape.region.download import region_for                            # noqa: E402
import routeshape.street_scale as ss                                        # noqa: E402
import routeshape.recognition as rc                                         # noqa: E402
from routeshape.wander import wander                                  # noqa: E402
from routeshape.shapes.library import resample_by_arclength                  # noqa: E402
from routeshape.metrics import alignment_angle, excursion                        # noqa: E402
from routeshape.export import to_gpx                                  # noqa: E402
from routeshape.shapes.library import SHAPES, register                       # noqa: E402
import routeshape.shapes.pack as shape_pack                                                # noqa: E402
import routeshape.shapes.emoji as emoji_pack                                              # noqa: E402
import routeshape.shapes.emoji_index as emoji_index                                      # noqa: E402
import server.store as store                                                             # noqa: E402
import routeshape.describe as describe_shape                                            # noqa: E402

# The wider library. Registered at import so /api/shapes lists them and the
# search treats them exactly like the original five - POC 30 fitted every one
# in Taipei and they came out 0.050 to 0.146.
shape_pack.install()

# The traced emoji, for the subjects nobody drew by hand. ONE drawing per
# subject reaches the page: three cards all labelled 貓 is not a choice a rider
# can make, and POC 37 says which one to keep anyway. Two raters saw all twelve
# subjects that exist in both, and hand against Noto split on NOTHING (12 pairs,
# 0 splits) - the traced version is not better, so there is no reason to
# replace a drawing that already works.
#
# NOTO AND NOT OPENMOJI, which is the opposite of what the outlines look like.
# The SVG gives the gear a bore and the ghost two eyes, and it still lost 5-0
# on the split pairs (p = 0.062): its extra interior detail is finer than the
# street grid, so it survives in the outline and is ground off in the route.
# It stays in the library for experiments and off the page until a rater round
# says otherwise.
# WITHDRAWN_SUBJECTS counts too, and the distinction matters. Taking a shape
# out of PACK would otherwise promote its traced twin to "a subject nobody drew
# by hand" and put the subject straight back on the page - `e_leaf` and
# `e_snowman` would have returned that way, and three raters failed to name
# them in EVERY arm. A withdrawal is about the SUBJECT. Losing to tracing is
# not: the crab and the giraffe left PACK because the traced version BEAT what
# I drew, and the traced version is exactly what belongs here.
EMOJI_ONLY = [name for name in emoji_pack.PACK
              if name not in shape_pack.PACK
              and name not in shape_pack.WITHDRAWN_SUBJECTS]
emoji_pack.install(names=EMOJI_ONLY)

LABELS = {"heart": "愛心", "star5": "五角星", "crescent": "月亮",
          "triangle": "三角形", "trex": "恐龍"}
LABELS.update(shape_pack.LABELS)
LABELS.update({"e_" + name: emoji_pack.LABELS[name] for name in EMOJI_ONLY})
# POC 17 fitted six candidates per shape and found the coarse scan's rank
# uncorrelated with the final result (Spearman -0.024 over thirty candidates).
# The pre-ranking says which placements are routable, not which are good, so the
# only way to find the good one is to fit more of them. Best-of-3 leaves two of
# five shapes above the 0.10 a person can see; best-of-6 leaves none. It costs
# linear time, and that is the whole trade.
N_CANDIDATES = 6
# How much wider than the shape the network is built. 1.0 gives half a shape
# width of slack on every side.
PLACEMENT_SLACK = 1.0
# Beyond this the stitch, the street index and the search stop being worth
# waiting for on a request. A 100 km heart is 24.9 km wide and lands here.
MAX_HALF_SIZE_M = 20000.0

# Somewhere to start from. Not a list of everywhere that works - any lat/lon in
# a downloaded region is routable - just the places worth offering as a first
# click. /api/places reports which of them the map actually reaches, so the
# page never offers a city whose tiles are not on disk.
PLACES = [
    ("台北", 25.0400, 121.5400), ("板橋", 25.0143, 121.4672),
    ("基隆", 25.1283, 121.7419), ("桃園", 24.9937, 121.3010),
    ("新竹", 24.8039, 120.9715), ("宜蘭", 24.7570, 121.7530),
    ("台中", 24.1477, 120.6736), ("彰化", 24.0809, 120.5387),
    ("嘉義", 23.4801, 120.4491), ("台南", 22.9908, 120.2133),
    ("高雄", 22.6273, 120.3014), ("屏東", 22.6690, 120.4880),
    ("花蓮", 23.9872, 121.6015), ("台東", 22.7583, 121.1444),
]
# The size a place is judged routable at. A place that cannot hold the smallest
# useful shape is not worth offering, and one that holds this holds most.
PLACE_PROBE_M = 4500.0

# Two raters, seventeen of seventeen, preferred a shape with a feature amputated
# over one of the same shape distance that wobbled everywhere (POC 18), and no
# weighting of the two reproduces their answers - so wander is not a term to
# trade off, it is a condition to meet. POC 19 then measured that among fitted
# routes wander and shape distance are essentially independent (Spearman +0.10,
# p = 0.52), which is what makes a constraint the right shape for it: you cannot
# get one by optimising the other.
#
# 0.30 is where the sweep sits: it cuts mean wander from 0.263 to 0.240 for
# +0.001 of shape distance across the five shapes. Tighter is worse - 0.25 costs
# +0.013 and pushes one shape back over the 0.10 a person can see.
#
# What this is NOT: evidence that the difference is visible. The raters compared
# curves whose better member had wander 0, and every real route here sits
# between 0.19 and 0.50. Extrapolating their preference down to 0.263 against
# 0.240 is not something the data supports.
WANDER_LIMIT = 0.30

# The farthest a route may stray from its template at any ONE point, as a
# fraction of the shape's width. A rater looked at a perfect Taiwan with one
# straight bar shot across the bottom right and answered "cannot tell", naming
# the bar; three of the six Taiwan routes in POC 33 carried one.
#
# Neither existing check can see it. `shape_distance` compares resampled
# positions, so a spike moves a handful of points; `wander` is a length ratio
# over the whole route, and 1 km of spur on a 25 km ride is 4% against the 30%
# above. Both are averages. A spur is a maximum.
#
# Measured over 126 answers from three raters, naming rate by excursion:
#
#     0.000-0.040   67%        0.070-0.090   52%
#     0.040-0.055   74%        0.090-1.000   21%
#     0.055-0.070   67%
#
# The cliff is at 0.09. 0.08 is the operating point: it keeps 71% of fitted
# placements, which were named 67% of the time against 25% for the ones it
# drops, and with six candidates per request there is nearly always one under
# it. It is applied like WANDER_LIMIT - lexicographically, falling back to the
# whole list rather than refusing, because a spurred route still beats none.
#
# This is the first constraint here fitted to what people RECOGNISE rather than
# to what the metric scores, and it had to be: within a fixed shape-distance
# band excursion still separates named from unnamed (p = 0.0009 below 0.10,
# p = 0.0001 above), while shape distance on its own manages p = 0.087.
EXCURSION_LIMIT = 0.08
MAX_TEXT = 12
ROUTES: dict[str, dict] = {}
_networks: dict[tuple, dict] = {}
_lock = threading.Lock()

# THE SEARCH IS DETERMINISTIC, so asking for the same route twice is pure
# waste. The coarse scan ranks a fixed grid, `select_candidates` takes the top
# few, and the Viterbi has no random component: the same request came back
# byte-identical twice in a row - 24.5 km, distance 0.166, rotation 60 - having
# spent 6.6 seconds arriving at it the second time. A fish at 30 km spends 53.
#
# Keyed on everything the answer depends on. Latitude and longitude are rounded
# to four places, about 11 m, because the page sends a city's coordinates and a
# rider's own position never repeats exactly anyway; a difference smaller than
# that cannot move a placement grid stepped in hundreds of metres.
#
# It never expires. The entries are a few hundred KB each, the shape library is
# 26 and the place list is 14, so the whole reachable space at the four preset
# distances is about 1,500 routes - and `ROUTES`, which holds the GPX each one
# points at, already lives for the life of the process. A cache that outlives
# its GPX would hand out a download link that 404s; this one cannot.
_ROUTE_CACHE: dict[tuple, dict] = {}

# And on disk, so a restart does not make the first rider pay again for a route
# the server has already found. See server/store.py for what is kept and why
# the street background is not.
STORE_PATH = HERE.parent / "_routes.db"
_store: "store.Store | None" = None


def _cache_key(shape: str, target_km: float, mode: str,
               lat: float, lon: float) -> tuple:
    return (shape, round(float(target_km), 1), mode,
            round(float(lat), 4), round(float(lon), 4))


def network(lat: float, lon: float, mode: str,
            half_size_m: float = NETWORK_HALF_SIZE_M) -> dict:
    """The street network for one place, mode and size, loaded at most once.

    The size has to be an argument. Fixed at NETWORK_HALF_SIZE_M the service
    built the same 9 km box whatever was asked of it, so every shape wider than
    about 6 km had nowhere to sit: a 50 km heart is 12.4 km across and came
    back "no placement" after 19 seconds of stitching, while `plan` had already
    answered "feasible". 30, 50 and 100 km are the distances this is for.
    """
    key = (round(lat, 4), round(lon, 4), mode, round(half_size_m))
    with _lock:
        if key not in _networks:
            t0 = time.time()
            # Prefer the regional cache: it covers anywhere in the region and
            # costs a stitch rather than a download, which is what makes "let
            # the user pick where they are" possible at all. Falls back to the
            # per-point downloader where the region has no tiles yet.
            try:
                graph = region_graph(lat, lon, half_size_m, mode=mode)
                source = "region cache"
            except FileNotFoundError:
                graph = download_walk_graph(lat, lon, half_size_m, mode=mode)
                source = "per-point download"
            to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"],
                                           always_xy=True)
            _networks[key] = {
                "graph": graph,
                "tree": build_street_index(graph),
                "region": np.array(to_proj.transform(lon, lat)),
                "crs": graph.graph["crs"],
                "load_seconds": round(time.time() - t0, 1),
                "source": source,
            }
            print(f"  loaded {mode} network for {lat},{lon} from {source} in "
                  f"{_networks[key]['load_seconds']}s "
                  f"({graph.number_of_nodes():,} nodes)", flush=True)
        return _networks[key]


def text_shape(text: str) -> str:
    """
    Register a word as a shape the rest of the pipeline can draw.

    The letterforms are traced, their contours joined into one closed curve
    (`multi_contour`), and the result registered under a name derived from the
    text, so `route_feasibility` and the search treat it exactly like a heart.

    Cached on the name: `n_min` is memoised per name, so re-registering a
    different curve under one name would serve a stale answer.
    """
    key = "text_" + "".join(c if c.isalnum() else "_" for c in text.upper())
    if key not in SHAPES:
        register(key, mc.text_curve(text.upper(), "outline"))
    return key


def is_text(shape: str) -> bool:
    return shape.startswith("text_")


def rotations_for(shape: str) -> tuple:
    """
    Text is the one shape family that is not rotation-invariant.

    POC 12 measured it: with rotation free the search returns tilted
    placements, `shape_distance` scores them BETTER than upright ones, and
    nobody can read them. So a word is pinned upright and everything else keeps
    the full sweep.
    """
    return (0.0,) if is_text(shape) else ROTATIONS_DEG


def streets_near(net: dict, xy: np.ndarray, pad_m: float = 400.0) -> list:
    """
    Every street around the route, as lat/lon polylines.

    The page needs a map behind the route or the shape is floating in nothing,
    and the obvious way to get one is a tile provider. This project already
    holds the streets it fitted to, so it draws those instead: no tile server,
    no API key, nothing to be blocked or rate-limited, and what the reader sees
    is exactly the network the route was matched against rather than a
    different rendering of the same city.
    """
    lo = xy.min(axis=0) - pad_m
    hi = xy.max(axis=0) + pad_m
    to_wgs = Transformer.from_crs(net["crs"], "EPSG:4326", always_xy=True)
    out = []
    for u, v, data in net["graph"].edges(data=True):
        geom = data.get("geometry")
        if geom is not None:
            xs, ys = np.asarray(geom.xy[0]), np.asarray(geom.xy[1])
        else:
            nodes = net["graph"].nodes
            xs = np.array([nodes[u]["x"], nodes[v]["x"]])
            ys = np.array([nodes[u]["y"], nodes[v]["y"]])
        if xs.max() < lo[0] or xs.min() > hi[0] or ys.max() < lo[1] or ys.min() > hi[1]:
            continue
        lons, lats = to_wgs.transform(xs, ys)
        out.append([[round(a, 5), round(b, 5)] for a, b in zip(lats, lons)])
    return out


def describe(body: dict) -> dict:
    """Turn a typed description into a shape the rest of the pipeline can draw.

    Claude proposes the outline; describe_shape.check decides whether it is
    rideable, and a failure goes back to the model with the reason rather than
    being repaired here. A shape that passes is registered under its own name,
    so the search and the fit treat it exactly like a built-in.
    """
    text = (body.get("description") or "").strip()
    if not text:
        return {"status": "error", "reason": "no description"}
    if len(text) > 200:
        return {"status": "error", "reason": "description too long"}
    mode = body.get("mode", rf.DEFAULT_MODE)
    lat = float(body.get("lat", SEARCH_LAT))
    lon = float(body.get("lon", SEARCH_LON))
    scale = ss.scale_for(lat, lon, mode, rf.MODES[mode]["street_scale_m"])
    backend = body.get("backend", describe_shape.DEFAULT_BACKEND)
    try:
        result = describe_shape.propose(text, mode, scale, backend=backend)
    except Exception as exc:      # noqa: BLE001 - missing key, network, quota
        # No credentials is the normal case for a local run, so it is reported
        # as a plain state rather than a 500 - the page keeps working on the
        # built-in library.
        return {"status": "unavailable", "backend": backend,
                "reason": type(exc).__name__, "detail": str(exc)[:300]}
    if result.get("status") != "ok":
        return result
    name = "gen_" + re.sub(r"[^a-z0-9_]", "", result["name"].lower())[:24]
    register(name, np.asarray(result["points"], dtype=float))
    LABELS[name] = result.get("label") or text[:12]
    return {**result, "shape": name,
            "min_km": round(rf.min_distance_km(name, mode, scale), 1),
            "recognition_measured": False}


def search(query: str, mode: str, lat: float, lon: float,
           limit: int = emoji_index.MAX_HITS) -> dict:
    """Typed words to shapes, out of every emoji the font can draw.

    A SECOND, OFFLINE PATH, deliberately not the one in `describe`. That one
    asks a model to invent an outline, which needs credentials and produces a
    drawing nobody has checked; this one searches 1,266 pictures that already
    passed the tracer, `describe.check` and `feasibility` at build time. A
    rider typing 狗 gets an answer in milliseconds and cannot reach a crash.

    The minimum distance is recomputed here rather than read from the index,
    because the index was built on Taipei's street scale and a rider in Keelung
    is asking about Keelung's.
    """
    scale = ss.scale_for(lat, lon, mode, rf.MODES[mode]["street_scale_m"])
    if not emoji_index.load()["emoji"]:
        return {"query": query, "hits": [], "problem": "index",
                "message": "emoji 索引沒有載入。"
                           "routeshape/shapes/emoji_index.json 不在，"
                           "或是還沒 git pull 到那個 commit。"}
    matched = emoji_index.find(query, limit)
    hits, undrawable = [], 0
    for row in matched:
        name = emoji_index.register(row["c"])
        if name is None:
            # FOUND BUT NOT DRAWABLE, which is not the same as not found and
            # must not be reported as it. The index was built on a machine with
            # the emoji font; this one may not have it.
            undrawable += 1
            continue
        LABELS.setdefault(name, row["n"])
        hits.append({"name": name, "emoji": row["c"], "label": row["n"],
                     "n_min": rf.n_min(name),
                     "min_km": round(rf.min_distance_km(name, mode, scale), 1),
                     "outline": outline_for(name),
                     "recognition_measured": rc.observed(name) is not None,
                     "recognition_seen": rc.observed(name)})
    out = {"query": query, "mode": mode, "street_scale_m": round(scale),
           "hits": hits, "matched": len(matched)}
    if not hits and undrawable:
        out["problem"] = "font"
        out["message"] = f"找到 {undrawable} 個，但這台機器畫不出來：" \
                         + emoji_pack.INSTALL_HINT
    return out


def places() -> list[dict]:
    """The starting points on offer, each marked with whether the map has it.

    Coverage is checked rather than assumed. The regions download over hours
    and a half-finished one would otherwise be offered as ready, sending the
    rider into a 'no placement' after a minute of stitching.
    """
    out = []
    for name, lat, lon in PLACES:
        region = region_for(lat, lon)
        covered = False
        if region:
            box = box_around(lat, lon, PLACE_PROBE_M)
            names = regions_overlapping(box) or [region]
            tiles = tiles_for(box, region, rf.DEFAULT_MODE)
            covered = bool(tiles) and coverage(
                box, tiles, fetched=fetched_bounds(names, rf.DEFAULT_MODE)
            ) >= MIN_COVERAGE
        out.append({"name": name, "lat": lat, "lon": lon,
                    "region": region, "ready": covered})
    return out


# Fidelity is reported as a measured recognition rate, per shape, from POC 29:
# 120 judgements by four raters naming real routes with no reference shown.
# See recognition.py - the thresholds are per shape because one threshold fits
# the same data far worse (chi2(4) = 28.7, p = 9.1e-06) and the 50% points run
# 0.120 to 0.321 across the five shapes.


_OUTLINES: dict[str, list] = {}


def outline_for(shape: str, points: int = 48) -> list:
    """A thumbnail of the shape itself, normalised and rounded.

    The shape cards carried a label, a minimum distance and a point count, and
    a rider picking 「錨」 had no way to know what this project's anchor looks
    like - or that the gear has its centre ring, which is the one thing the
    rider asked for by name. The outlines are tiny and never change, so they
    are computed once and held.
    """
    if shape not in _OUTLINES:
        xy = resample_by_arclength(shape, points)
        span = float(max(xy.max(axis=0) - xy.min(axis=0))) or 1.0
        xy = (xy - xy.mean(axis=0)) / span
        _OUTLINES[shape] = [[round(float(a), 3), round(float(b), 3)]
                            for a, b in xy]
    return _OUTLINES[shape]


def quality_for(shape: str) -> tuple[str, str]:
    """How this route came out, in the counts of people who named the shape.

    Took `distance` until POC 39, which pooled 311 judgements and found that a
    a curve over shape_distance predicts a held-out answer no better than
    knowing nothing at all (log-loss 0.656 against 0.660), and neither does
    excursion. Which drawing it is cuts the loss to 0.505. So the answer is
    the shape's measured rate and nothing about this particular route - and
    "no answer" for a shape nobody has rated, rather than a pooled average
    borrowed from other shapes. The route-specific warnings the page shows
    come from the wander and excursion LIMITS, which are a different question:
    whether the fit met its own constraints, not whether anyone will name it.
    """
    return rc.verdict(shape)


def plan(shape: str, target_km: float, mode: str,
         street_scale_m: float | None = None) -> dict:
    """The feasibility answer, which needs no map and returns immediately."""
    p = rf.plan(shape, target_km, mode, street_scale_m)
    feasible, message = p.feasible, p.reason
    # route_feasibility only knows the LOWER bound - the shape needs enough
    # points to be recognisable. There is an upper bound too and it lives here,
    # because it is a property of the served map rather than of the shape: a
    # 200 km heart is 49.7 km across and no network we will build holds it. The
    # service used to answer "feasible" to that and then spend 19 seconds
    # stitching before returning "no placement", which is a worse answer than
    # no for having taken longer.
    if feasible and p.width_m and p.width_m * PLACEMENT_SLACK > MAX_HALF_SIZE_M:
        max_km = target_km * MAX_HALF_SIZE_M / (p.width_m * PLACEMENT_SLACK)
        feasible = False
        message = (f"{p.width_m / 1000:.0f} km wide - too big to place. "
                   f"This shape tops out near {max_km:.0f} km.")
    return {"shape": shape,
            "label": LABELS.get(shape, shape.replace("text_", "").replace("_", " ")),
            "is_text": is_text(shape), "mode": mode,
            "target_km": target_km, "feasible": feasible,
            "n_min": rf.n_min(shape), "points": p.points,
            "min_km": round(p.min_km, 1),
            "street_scale_m": round(street_scale_m) if street_scale_m else None,
            "width_m": round(p.width_m) if p.width_m else None,
            "message": message,
            "estimate_km": ([round(x, 1) for x in p.range_km]
                            if p.range_km else None)}


def build_route(shape: str, target_km: float, mode: str,
                lat: float, lon: float, force: bool = False) -> dict:
    """Search the city for the best placement, fit a route, keep the GPX.

    Cached on the request, because the search is deterministic - see
    `_ROUTE_CACHE`. `force` skips the cache and replaces the entry; it was
    already accepted and ignored by this endpoint, and this is what it meant.
    """
    key = _cache_key(shape, target_km, mode, lat, lon)
    if not force:
        with _lock:
            hit = _ROUTE_CACHE.get(key)
        if hit is not None:
            # A copy, so a caller mutating the answer cannot poison the cache,
            # and with the timing told straight: `seconds` is what THIS request
            # cost. Reporting the original 53 seconds for a reply that took a
            # millisecond would be a lie in the one field that exists to say
            # how long the work took.
            return dict(_rehydrate(hit, mode), seconds=0.0, cached=True)

    answer = _build_route_uncached(shape, target_km, mode, lat, lon, force)
    if answer.get("status") == "ok":
        with _lock:
            _ROUTE_CACHE[key] = answer
        if _store is not None:
            _store.put(key, answer)
    return dict(answer, cached=False)


def _rehydrate(answer: dict, mode: str) -> dict:
    """Put back what the store does not keep.

    A route restored from disk has no street background and no GPX waiting
    under its id - both are derived from the route and the network, and both
    are far cheaper to rebuild than to store. The GPX is built from the route's
    own WGS84 coordinates, so this needs no projection and no graph.
    """
    answer = dict(answer)
    route_id = answer.get("id")
    if route_id and route_id not in ROUTES:
        pts = np.array([[lon, lat] for lat, lon in answer.get("coordinates", [])])
        if len(pts):
            label = answer.get("label", answer.get("shape", ""))
            ROUTES[route_id] = {
                "gpx": to_gpx(pts, "EPSG:4326", f"{label}路線",
                              f"{label} · {answer.get('route_km')} km · {mode}"),
                "shape": answer.get("shape", "")}
    if "streets" not in answer and answer.get("coordinates"):
        try:
            net = network(answer["_lat"], answer["_lon"], mode) \
                if "_lat" in answer else None
        except Exception:                                # noqa: BLE001
            net = None
        if net is not None:
            to_xy = Transformer.from_crs("EPSG:4326", net["crs"], always_xy=True)
            lons, lats = zip(*[(lon, lat) for lat, lon in answer["coordinates"]])
            xs, ys = to_xy.transform(lons, lats)
            answer["streets"] = streets_near(net, np.column_stack([xs, ys]))
    return answer


def _build_route_uncached(shape: str, target_km: float, mode: str,
                          lat: float, lon: float, force: bool = False) -> dict:
    """The search itself. Everything below this line is unchanged."""
    # MEASURE FIRST, then size. The street scale decides how wide the shape is
    # drawn, and the width decides how big a network to load - so measuring
    # after loading gets the order backwards. It did: a first visit to a new
    # place downloaded the full-size network on the national default scale,
    # THEN downloaded a 5 km probe to measure, then re-planned. A rider in
    # Xinyi waited 58.5s and then another 35.7s for that, and the big download
    # was sized on a number already known to be provisional.
    #
    # It also closes a latent bug: the old code kept using the network it had
    # already loaded after re-planning to a different width, which was only
    # safe because measured scales happen to come out at or above the default.
    #
    # The probe is a FIXED 5 km box, so it is not always the smaller of the two
    # - for a small shape it is the larger, and for those the shape's own box
    # fits inside it and is reused rather than loaded again.
    probe = None
    if not ss.is_measured(lat, lon, mode):
        probe = network(lat, lon, mode, ss.MEASURE_HALF_M)
        local_scale = ss.scale_for(lat, lon, mode,
                                   rf.MODES[mode]["street_scale_m"], probe["graph"])
    else:
        local_scale = ss.scale_for(lat, lon, mode, rf.MODES[mode]["street_scale_m"])

    verdict = plan(shape, target_km, mode, local_scale)
    if not verdict["feasible"]:
        return {"status": "infeasible", **verdict}

    width_m = float(verdict["width_m"])
    points = int(verdict["points"])
    # Room for the shape and room to move it: a network only as wide as the
    # shape leaves one placement, and POC 23 found that a route with no choice
    # of placement pays roughly double the detour of one chosen from thousands.
    half_size = max(NETWORK_HALF_SIZE_M, width_m * PLACEMENT_SLACK)
    # Same centre, so a probe at least as wide already contains this box.
    net = (probe if probe is not None and ss.MEASURE_HALF_M >= half_size
           else network(lat, lon, mode, half_size))
    t0 = time.time()

    margin = max(400.0, half_size - width_m * 0.75)
    centers, _, _ = build_center_grid(net["region"], margin, GRID_STEP_M)
    rotations = rotations_for(shape)
    scored = coarse_scan(net["tree"], centers, shape, width_m, rotations)
    viable = int(np.isfinite(scored["score"]).sum())
    if viable == 0:
        return {"status": "no placement", **verdict}
    # POC 27 stopped here when fewer than half the placements fitted, on the
    # basis that such routes came out at 0.18 or worse and 0.18 meant unusable.
    # POC 29 then MEASURED unusable and it is not 0.18, it is per shape - and
    # under that criterion this check blocked Taipei's 35 km and 50 km hearts,
    # which are recognised by essentially everyone, while the three genuinely
    # unrecognisable routes do not separate from them by viable rate at all
    # (worst unusable 22.0%, lowest usable 9.7%, gap -12.3%). The signal itself
    # is real - log viable rate against shape distance is r = -0.85 - but it
    # cannot carry a gate, and all three unusable cases came from one city, so
    # there is nothing here to recalibrate on either. Removed rather than
    # retuned; `force` is still accepted and ignored.

    dense_template = resample_by_arclength(shape, 4000)
    fitted = []
    for row in select_candidates(scored, N_CANDIDATES, MIN_SEPARATION_M):
        try:
            fit = refine(net["graph"], shape, np.array([row["x"], row["y"]]),
                         row["rotation"], width_m, points=points)
        except NoRouteFoundError:
            continue
        if fit is None:
            continue
        closed_template = np.vstack([dense_template, dense_template[:1]])
        centre = np.array([row["x"], row["y"]])
        # Wander is a length ratio, so the template's ORIENTATION does not
        # matter to it and this call has always passed 0. Excursion is a
        # nearest-point distance and orientation is most of it: measured
        # against an upright template a correctly fitted Taiwan scored 0.253,
        # which is the rotation, not a spur. It gets the template the matcher
        # actually aimed at.
        fit["wander"] = wander(fit["route_xy"],
                               place_shape(closed_template, centre, width_m, 0.0))
        fit["excursion"] = excursion(
            fit["route_xy"],
            place_shape(closed_template, centre, width_m, row["rotation"]))
        fitted.append(fit)
        # Stop once one candidate is comfortably recognisable. Fitting is the
        # whole cost of a request - six candidates on a 55 km Taiwan took 144
        # seconds - and POC 24 measured what the extra ones buy: going from
        # three to six moves the shape distance by 0.009 at 10 km and 0.008 at
        # 50 km, against a 0.10 threshold at which a person first sees any
        # difference at all. Roughly a twelfth of the smallest visible change,
        # for double the wait.
        #
        # Stopping on the RESULT rather than on a fixed count, because POC 17
        # showed the coarse scan cannot say which placement will be good: the
        # first candidate is effectively random, so the saving only appears
        # when one happens to come out well, and a hard case still uses all
        # six. The bar is the per-shape recognition curve from POC 29, so a
        # triangle has to come out tighter than a star to qualify.
        # Stop when the route is at least as tight as the ones raters were
        # shown for this shape - see recognition.as_good_as_rated. A fixed bar
        # on a measured rate would only be testing how many people have seen
        # the shape, because a rate from thirteen answers cannot reach 0.97
        # however good the route is.
        if (fit["wander"] <= WANDER_LIMIT
                and fit["excursion"] <= EXCURSION_LIMIT
                and rc.as_good_as_rated(shape, float(fit["excursion"]))):
            break

    if not fitted:
        return {"status": "no route", **verdict}

    # Lexicographic, not weighted: meet the wander condition first, then pick the
    # closest shape among those that do. Falling back to the whole list rather
    # than refusing - a route that wanders is still better than no route.
    admissible = ([f for f in fitted if f["wander"] <= WANDER_LIMIT
                   and f["excursion"] <= EXCURSION_LIMIT]
                  or [f for f in fitted if f["excursion"] <= EXCURSION_LIMIT]
                  or [f for f in fitted if f["wander"] <= WANDER_LIMIT]
                  or fitted)
    best = min(admissible, key=lambda f: f["distance"])

    dense = resample_by_arclength(shape, 4000)
    upright = place_shape(np.vstack([dense, dense[:1]]),
                          best["centre_xy"], width_m, 0.0)

    route_id = uuid.uuid4().hex[:12]
    km = best["metrics"]["route_km"]
    description = (f"{shape} · {km:.1f} km · {mode} · "
                   f"shape distance {best['distance']:.3f}")
    ROUTES[route_id] = {
        "gpx": to_gpx(best["route_xy"], net["crs"],
                      f"{LABELS.get(shape, shape)}路線", description),
        "shape": shape,
    }
    to_wgs = Transformer.from_crs(net["crs"], "EPSG:4326", always_xy=True)
    lons, lats = to_wgs.transform(best["route_xy"][:, 0], best["route_xy"][:, 1])
    return {"status": "ok", **verdict, "id": route_id,
            # Two different angles, and only the second one is any use for
            # drawing. `rotation_deg` is what the search ASKED for.
            # `upright_deg` is what the finished route actually turned out to
            # be, read back out of the metric's own alignment - the route is a
            # walk over streets approximating the template, not the template,
            # so its own orientation drifts from the request.
            "rotation_deg": round(float(best["rotation"]), 1),
            # Where to reload the network from when this comes back off disk
            # without its street background.
            "_lat": lat, "_lon": lon,
            "quality": quality_for(shape)[0],
            "quality_message": quality_for(shape)[1],
            "recognition": (None if rc.rate(shape) is None
                            else round(rc.rate(shape), 2)),
            "recognition_measured": rc.observed(shape) is not None,
            "recognition_seen": rc.observed(shape),
            "wander": round(float(best["wander"]), 3),
            "wander_limit": WANDER_LIMIT,
            "excursion": round(float(best["excursion"]), 3),
            "excursion_limit": EXCURSION_LIMIT,
            "candidates_within_limit": sum(f["wander"] <= WANDER_LIMIT
                                           for f in fitted),
            "upright_deg": round(alignment_angle(best["route_xy"], upright), 1),
            "route_km": round(km, 1),
            "shape_distance": round(best["distance"], 3),
            "seconds": round(time.time() - t0, 1),
            "coordinates": [[round(a, 6), round(b, 6)]
                            for a, b in zip(lats, lons)],
            "streets": streets_near(net, best["route_xy"]),
            "gpx_url": f"/api/route/{route_id}.gpx"}


class Handler(BaseHTTPRequestHandler):
    server_version = "shape-route/1.0"

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}", flush=True)

    def _send(self, code: int, body: bytes, content_type: str,
              filename: str | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition",
                             f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif path == "/api/shapes":
            q = parse_qs(urlparse(self.path).query)
            mode = q.get("mode", ["bike"])[0]
            # The floors are per place, not national: Keelung's streets are
            # 439 m apart against Taipei's 280, so its smallest drawable heart
            # is 7.8 km rather than 3.7. Reporting Taipei's floor on a Keelung
            # card would offer a shape the planner then refuses.
            try:
                lat = float(q.get("lat", [SEARCH_LAT])[0])
                lon = float(q.get("lon", [SEARCH_LON])[0])
            except ValueError:
                lat, lon = SEARCH_LAT, SEARCH_LON
            scale = ss.scale_for(lat, lon, mode, rf.MODES[mode]["street_scale_m"])
            self._json(200, {"mode": mode, "street_scale_m": round(scale),
                             "shapes": [
                {"name": s, "label": LABELS.get(s, s), "n_min": rf.n_min(s),
                 "min_km": round(rf.min_distance_km(s, mode, scale), 1),
                 # The picture, so the card is not asking a rider to choose
                 # 「錨」 from its name and a point count. 48 points is enough
                 # for a thumbnail and keeps the whole list under 60 KB.
                 "outline": outline_for(s),
                 "recognition_measured": rc.observed(s) is not None,
                 "recognition_seen": rc.observed(s)}
                for s in sorted(SHAPES, key=rf.n_min)]})
        elif path == "/api/places":
            self._json(200, {"places": places()})

        elif path.startswith("/api/route/") and path.endswith(".gpx"):
            route_id = path[len("/api/route/"):-len(".gpx")]
            entry = ROUTES.get(route_id)
            if entry is None:
                self._json(404, {"error": "route not found or expired"})
            else:
                self._send(200, entry["gpx"].encode("utf-8"),
                           "application/gpx+xml; charset=utf-8",
                           filename=f"{entry['shape']}.gpx")
        else:
            self._json(404, {"error": "no such endpoint"})

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "body must be JSON"})
            return

        mode = body.get("mode", rf.DEFAULT_MODE)
        text = (body.get("text") or "").strip()
        if text:
            if len(text) > MAX_TEXT:
                self._json(400, {"error": f"最多 {MAX_TEXT} 個字元"})
                return
            try:
                shape = text_shape(text)
            except (KeyError, ValueError) as exc:
                self._json(400, {"error": f"畫不出來：{exc}。"
                                          "目前的字型只有拉丁字母、數字和標點。"})
                return
        else:
            shape = body.get("shape", "heart")
            if shape not in SHAPES:
                self._json(400, {"error": f"unknown shape {shape!r}"})
                return
        if mode not in rf.MODES:
            self._json(400, {"error": f"unknown mode {mode!r}"})
            return
        try:
            target_km = float(body.get("target_km", 10))
        except (TypeError, ValueError):
            self._json(400, {"error": "target_km must be a number"})
            return

        # A rider can ask for a shape by the emoji itself. Resolving it here
        # means /api/plan and /api/route need no branch of their own - by the
        # time they run it is an ordinary registered shape.
        if body.get("emoji"):
            resolved = emoji_index.register(str(body["emoji"])[:8])
            if resolved is None:
                self._json(200, {"status": "error",
                                 "message": "這個 emoji 畫不出來"})
                return
            LABELS.setdefault(resolved, emoji_index.label(str(body["emoji"])[:8]))
            body["shape"] = resolved
            shape = resolved

        try:
            if path == "/api/search":
                self._json(200, search(
                    str(body.get("query", ""))[:40],
                    body.get("mode", rf.DEFAULT_MODE),
                    float(body.get("lat", SEARCH_LAT)),
                    float(body.get("lon", SEARCH_LON))))
                return

            if path == "/api/describe":
                self._json(200, describe(body))
                return

            if path == "/api/plan":
                lat = float(body.get("lat", SEARCH_LAT))
                lon = float(body.get("lon", SEARCH_LON))
                self._json(200, plan(shape, target_km, mode,
                                     ss.scale_for(lat, lon, mode,
                                                  rf.MODES[mode]["street_scale_m"])))
            elif path == "/api/route":
                self._json(200, build_route(
                    shape, target_km, mode,
                    float(body.get("lat", SEARCH_LAT)),
                    float(body.get("lon", SEARCH_LON)),
                    bool(body.get("force", False))))
            else:
                self._json(404, {"error": "no such endpoint"})
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "route build failed; see server log"})


# The four buttons on the page, which is what a rider actually picks.
PRESET_KM = (10.0, 30.0, 50.0, 100.0)


def precompute(lat: float = SEARCH_LAT, lon: float = SEARCH_LON,
               mode: str = "bike") -> None:
    """Fit everything the page can ask for at the preset distances.

    Only the presets, not the whole slider: the slider is continuous and the
    buttons are where the traffic is. A shape whose minimum is above the preset
    is skipped rather than fitted at a distance nobody can select.
    """
    scale = ss.scale_for(lat, lon, mode, rf.MODES[mode]["street_scale_m"])
    jobs = [(s, km) for s in sorted(SHAPES) for km in PRESET_KM
            if rf.min_distance_km(s, mode, scale) <= km]
    print(f"{len(jobs)} routes to fit; {len(SHAPES)} shapes over "
          f"{len(PRESET_KM)} distances", flush=True)
    done = 0
    for shape, km in jobs:
        key = _cache_key(shape, km, mode, lat, lon)
        if key in _ROUTE_CACHE:
            continue
        t0 = time.time()
        answer = build_route(shape, km, mode, lat, lon)
        done += 1
        print(f"  {shape:16s} {km:5.0f} km -> {answer.get('status')} "
              f"{answer.get('route_km', '')} ({time.time() - t0:.0f}s)",
              flush=True)
    print(f"{done} fitted, {_store.count() if _store else 0} in the database")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--warm", action="store_true",
                        help="load the default network before serving")
    parser.add_argument("--no-store", action="store_true",
                        help="do not read or write the route database")
    parser.add_argument("--precompute", action="store_true",
                        help="fit every shape at every preset distance for the "
                             "default place, fill the database, and exit")
    args = parser.parse_args()

    global _store
    if not args.no_store:
        _store = store.Store(STORE_PATH)
        restored, dropped = _store.load()
        _ROUTE_CACHE.update(restored)
        print(f"{len(restored)} routes restored from {STORE_PATH.name}"
              + (f", {dropped} dropped (the shape has been redrawn)"
                 if dropped else ""), flush=True)

    if args.precompute:
        precompute()
        return

    if args.warm:
        print("warming the network cache...", flush=True)
        network(SEARCH_LAT, SEARCH_LON, rf.DEFAULT_MODE)

    # Say what is actually loaded. The emoji font and the word index are both
    # things that can be absent on one machine and present on another, and both
    # failed silently into 「找不到」 before this line existed.
    installed = [n for n in SHAPES if n.startswith("e_")]
    print(f"{len(SHAPES)} shapes ({len(installed)} traced), "
          f"emoji font {emoji_pack.FONT or 'MISSING - ' + emoji_pack.INSTALL_HINT}, "
          f"{len(emoji_index.load()['emoji'])} emoji in the word index",
          flush=True)
    print(f"serving on http://{args.host}:{args.port}", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
