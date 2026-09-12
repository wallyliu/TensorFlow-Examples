"""
A small HTTP service that turns a shape and a distance into a route file.

Everything the pipeline does has been reachable only by running Python in a
terminal. This is the same pipeline behind three endpoints, so a page can ask
for a route and get a .gpx back.

Standard library only - no framework to install. That is a deliberate choice
for something a person has to be able to run in one command, not a limitation:
the work per request is 2-4 seconds of numpy and networkx, so the web layer is
never the bottleneck and a framework would only add a setup step.

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
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import multi_contour as mc                                      # noqa: E402
import route_feasibility as rf                                   # noqa: E402
from heart_route_poc import download_walk_graph                  # noqa: E402
from heart_route_poc2 import NoRouteFoundError                   # noqa: E402
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M,     # noqa: E402
                              NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON,
                              build_center_grid, build_street_index,
                              select_candidates)
from heart_route_poc3 import place_shape                          # noqa: E402
from poc6_shapes import ROTATIONS_DEG, coarse_scan, refine       # noqa: E402
from poc15_wiggle import wander                                  # noqa: E402
from shape_library import resample_by_arclength                  # noqa: E402
from shape_metrics import alignment_angle                        # noqa: E402
from route_export import to_gpx                                  # noqa: E402
from shape_library import SHAPES, register                       # noqa: E402

LABELS = {"heart": "愛心", "star5": "五角星", "crescent": "月亮",
          "triangle": "三角形", "trex": "恐龍"}
# POC 17 fitted six candidates per shape and found the coarse scan's rank
# uncorrelated with the final result (Spearman -0.024 over thirty candidates).
# The pre-ranking says which placements are routable, not which are good, so the
# only way to find the good one is to fit more of them. Best-of-3 leaves two of
# five shapes above the 0.10 a person can see; best-of-6 leaves none. It costs
# linear time, and that is the whole trade.
N_CANDIDATES = 6

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
MAX_TEXT = 12
ROUTES: dict[str, dict] = {}
_networks: dict[tuple, dict] = {}
_lock = threading.Lock()


def network(lat: float, lon: float, mode: str) -> dict:
    """The street network for one place and mode, loaded at most once."""
    key = (round(lat, 4), round(lon, 4), mode)
    with _lock:
        if key not in _networks:
            t0 = time.time()
            graph = download_walk_graph(lat, lon, NETWORK_HALF_SIZE_M, mode=mode)
            to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"],
                                           always_xy=True)
            _networks[key] = {
                "graph": graph,
                "tree": build_street_index(graph),
                "region": np.array(to_proj.transform(lon, lat)),
                "crs": graph.graph["crs"],
                "load_seconds": round(time.time() - t0, 1),
            }
            print(f"  loaded {mode} network for {lat},{lon} in "
                  f"{_networks[key]['load_seconds']}s", flush=True)
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


def plan(shape: str, target_km: float, mode: str) -> dict:
    """The feasibility answer, which needs no map and returns immediately."""
    p = rf.plan(shape, target_km, mode)
    return {"shape": shape,
            "label": LABELS.get(shape, shape.replace("text_", "").replace("_", " ")),
            "is_text": is_text(shape), "mode": mode,
            "target_km": target_km, "feasible": p.feasible,
            "n_min": rf.n_min(shape), "points": p.points,
            "min_km": round(p.min_km, 1),
            "width_m": round(p.width_m) if p.width_m else None,
            "message": p.reason,
            "estimate_km": ([round(x, 1) for x in p.range_km]
                            if p.range_km else None)}


def build_route(shape: str, target_km: float, mode: str,
                lat: float, lon: float) -> dict:
    """Search the city for the best placement, fit a route, keep the GPX."""
    verdict = plan(shape, target_km, mode)
    if not verdict["feasible"]:
        return {"status": "infeasible", **verdict}

    net = network(lat, lon, mode)
    width_m = float(verdict["width_m"])
    points = int(verdict["points"])
    t0 = time.time()

    margin = max(400.0, NETWORK_HALF_SIZE_M - width_m * 0.75)
    centers, _, _ = build_center_grid(net["region"], margin, GRID_STEP_M)
    scored = coarse_scan(net["tree"], centers, shape, width_m,
                         rotations_for(shape))
    if not np.isfinite(scored["score"]).any():
        return {"status": "no placement", **verdict}

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
        fit["wander"] = wander(
            fit["route_xy"],
            place_shape(np.vstack([dense_template, dense_template[:1]]),
                        np.array([row["x"], row["y"]]), width_m, 0.0))
        fitted.append(fit)

    if not fitted:
        return {"status": "no route", **verdict}

    # Lexicographic, not weighted: meet the wander condition first, then pick the
    # closest shape among those that do. Falling back to the whole list rather
    # than refusing - a route that wanders is still better than no route.
    admissible = [f for f in fitted if f["wander"] <= WANDER_LIMIT] or fitted
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
            "wander": round(float(best["wander"]), 3),
            "wander_limit": WANDER_LIMIT,
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
            mode = "bike"
            if "mode=" in self.path:
                mode = self.path.split("mode=")[1].split("&")[0]
            self._json(200, {"mode": mode, "shapes": [
                {"name": s, "label": LABELS.get(s, s), "n_min": rf.n_min(s),
                 "min_km": round(rf.min_distance_km(s, mode), 1)}
                for s in sorted(SHAPES, key=rf.n_min)]})
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

        try:
            if path == "/api/plan":
                self._json(200, plan(shape, target_km, mode))
            elif path == "/api/route":
                self._json(200, build_route(
                    shape, target_km, mode,
                    float(body.get("lat", SEARCH_LAT)),
                    float(body.get("lon", SEARCH_LON))))
            else:
                self._json(404, {"error": "no such endpoint"})
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "route build failed; see server log"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--warm", action="store_true",
                        help="load the default network before serving")
    args = parser.parse_args()

    if args.warm:
        print("warming the network cache...", flush=True)
        network(SEARCH_LAT, SEARCH_LON, rf.DEFAULT_MODE)

    print(f"serving on http://{args.host}:{args.port}", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
