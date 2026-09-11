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

import route_feasibility as rf                                   # noqa: E402
from heart_route_poc import download_walk_graph                  # noqa: E402
from heart_route_poc2 import NoRouteFoundError                   # noqa: E402
from heart_route_poc3 import (GRID_STEP_M, MIN_SEPARATION_M,     # noqa: E402
                              NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON,
                              build_center_grid, build_street_index,
                              select_candidates)
from poc6_shapes import ROTATIONS_DEG, coarse_scan, refine       # noqa: E402
from route_export import to_gpx                                  # noqa: E402
from shape_library import SHAPES                                 # noqa: E402

LABELS = {"heart": "愛心", "star5": "五角星", "crescent": "月亮",
          "triangle": "三角形", "trex": "恐龍"}
N_CANDIDATES = 3
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


def plan(shape: str, target_km: float, mode: str) -> dict:
    """The feasibility answer, which needs no map and returns immediately."""
    p = rf.plan(shape, target_km, mode)
    return {"shape": shape, "label": LABELS.get(shape, shape), "mode": mode,
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
    scored = coarse_scan(net["tree"], centers, shape, width_m, ROTATIONS_DEG)
    if not np.isfinite(scored["score"]).any():
        return {"status": "no placement", **verdict}

    best = None
    for row in select_candidates(scored, N_CANDIDATES, MIN_SEPARATION_M):
        try:
            fit = refine(net["graph"], shape, np.array([row["x"], row["y"]]),
                         row["rotation"], width_m, points=points)
        except NoRouteFoundError:
            continue
        if fit is not None and (best is None or fit["distance"] < best["distance"]):
            best = fit
    if best is None:
        return {"status": "no route", **verdict}

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
            "route_km": round(km, 1),
            "shape_distance": round(best["distance"], 3),
            "seconds": round(time.time() - t0, 1),
            "coordinates": [[round(a, 6), round(b, 6)]
                            for a, b in zip(lats, lons)],
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

        shape = body.get("shape", "heart")
        mode = body.get("mode", rf.DEFAULT_MODE)
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
