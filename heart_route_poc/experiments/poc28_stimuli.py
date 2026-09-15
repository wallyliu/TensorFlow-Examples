"""
Build the stimuli for measuring where a shape stops being recognisable.

BACKLOG #3, open since POC 6 and the oldest thing on the list. What has been
measured is the DISCRIMINATION threshold: 0.10 is where a person sees that two
routes differ. That is not the same question as whether anyone can tell what
the route is meant to be, and the project has repeatedly been careful to say
so - the service's own quality bands decline to promise recognisability for
exactly this reason.

Two faults have kept it unmeasured, and they have never been fixed in the same
task:

  ANCHORING. Every rater task so far showed the ideal shape beside the route.
  Once you have been told it is a heart you cannot un-know it, and the question
  becomes "how good a heart" - which is discrimination again.

  ONE SHAPE AT A TIME. Asking "is this a heart?" about a heart invites yes.
  Recognition means picking it out from the alternatives.

So: the rater sees a route alone, with no reference, and names it from every
shape in the library at once plus "none of these". Chance is 1/(k+1). The
threshold is the shape distance at which naming accuracy falls to chance.

This script only generates the stimuli. It fits each shape at several sizes and
in several cities and keeps EVERY candidate, not just the winner, because the
losers are where the high-distance stimuli come from - and they are real fitted
routes rather than synthetically degraded ones. POC 13 established that damage
and noise of equal metric distance are not equally damaging, so a synthetic
ladder would measure the wrong thing.

Run:  python poc28_stimuli.py
Out:  poc28_stimuli.json   (route point arrays + true shape + distance)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from pyproj import Transformer

import routeshape.feasibility as rf
import routeshape.shapes.library as sl
import routeshape.street_scale as ss
from routeshape.matching import NoRouteFoundError
from routeshape.placement import (GRID_STEP_M, MIN_SEPARATION_M, build_center_grid,
                              build_street_index, select_candidates)
from routeshape.search import coarse_scan, refine
from routeshape.region.graph import RegionNotCovered, region_graph
from routeshape.shapes.library import resample_by_arclength
from routeshape.metrics import alignment_angle
from routeshape.shapes.taipei101 import outline as t101_outline

MODE = "bike"
CANDIDATES = 6
PLACEMENT_SLACK = 1.0
# Sizes and places chosen to spread the distance, not to look good: the big
# sizes and the sparse cities are where the unrecognisable end comes from.
PLAN = [
    ("heart",    [(10.0, "台北", 25.0400, 121.5400), (35.0, "台北", 25.0400, 121.5400),
                  (10.0, "基隆", 25.1283, 121.7419), (10.0, "台中", 24.1477, 120.6736)]),
    ("crescent", [(10.0, "台北", 25.0400, 121.5400), (30.0, "台北", 25.0400, 121.5400),
                  (10.0, "基隆", 25.1283, 121.7419)]),
    ("triangle", [(10.0, "台北", 25.0400, 121.5400), (30.0, "台北", 25.0400, 121.5400),
                  (10.0, "宜蘭", 24.7570, 121.7530)]),
    ("star5",    [(20.0, "台北", 25.0400, 121.5400), (40.0, "台北", 25.0400, 121.5400),
                  (20.0, "桃園", 24.9937, 121.3010)]),
    ("trex",     [(50.0, "台北", 25.0400, 121.5400)]),
    ("taipei101",[(50.0, "台北", 25.0400, 121.5400)]),
]
OUT = Path(__file__).with_name("poc28_stimuli.json")

_nets: dict = {}


def net_for(lat, lon, half):
    key = (round(lat, 4), round(lon, 4), round(half))
    if key not in _nets:
        g = region_graph(lat, lon, half, mode=MODE)
        tp = Transformer.from_crs("EPSG:4326", g.graph["crs"], always_xy=True)
        _nets.clear()
        _nets[key] = {"graph": g, "tree": build_street_index(g),
                      "region": np.array(tp.transform(lon, lat))}
    return _nets[key]


def upright_points(route_xy, template, n=220) -> list:
    """The route turned upright and normalised, as a short point array.

    Turned upright because the metric ignores orientation, so a route the
    search happened to place at 140 degrees is not 'less recognisable' - it is
    the same route shown badly, and asking a rater to mentally rotate it
    measures mental rotation. Normalised so size and position carry no
    information either; only form is left, which is what the question is about.
    """
    angle = np.radians(alignment_angle(route_xy, template))
    rot = np.array([[np.cos(angle), -np.sin(angle)],
                    [np.sin(angle), np.cos(angle)]])
    xy = (route_xy - route_xy.mean(axis=0)) @ rot.T
    span = float(np.abs(xy).max())
    xy = xy / span if span > 0 else xy
    if len(xy) > n:
        idx = np.linspace(0, len(xy) - 1, n).round().astype(int)
        xy = xy[idx]
    return [[round(float(a), 4), round(float(b), 4)] for a, b in xy]


def main() -> None:
    sl.register("taipei101", t101_outline())
    out = []
    for shape, configs in PLAN:
        for target_km, city, lat, lon in configs:
            scale = ss.scale_for(lat, lon, MODE, rf.MODES[MODE]["street_scale_m"])
            p = rf.plan(shape, target_km, MODE, scale)
            if not p.feasible:
                print(f"  {shape}@{target_km:.0f}/{city}: {p.reason}", flush=True)
                continue
            width_m, points = float(p.width_m), int(p.points)
            dense = resample_by_arclength(shape, 4000)
            closed = np.vstack([dense, dense[:1]])
            half = max(4500.0, width_m * PLACEMENT_SLACK)
            try:
                net = net_for(lat, lon, half)
            except RegionNotCovered as exc:
                print(f"  {shape}@{target_km:.0f}/{city}: {exc}", flush=True)
                continue
            centers, _, _ = build_center_grid(
                net["region"], max(400.0, half - width_m * 0.75), GRID_STEP_M)
            scored = coarse_scan(net["tree"], centers, shape, width_m, (0.0,))
            if not np.isfinite(scored["score"]).any():
                print(f"  {shape}@{target_km:.0f}/{city}: no placement", flush=True)
                continue
            t0 = time.time()
            kept = 0
            for row in select_candidates(scored, CANDIDATES, MIN_SEPARATION_M):
                centre = np.array([row["x"], row["y"]])
                try:
                    f = refine(net["graph"], shape, centre, row["rotation"],
                               width_m, points=points)
                except NoRouteFoundError:
                    f = None
                if f is None:
                    continue
                from routeshape.placement import place_shape
                template = place_shape(closed, centre, width_m, 0.0)
                out.append({
                    "shape": shape, "city": city, "target_km": target_km,
                    "width_m": round(width_m), "points": points,
                    "distance": round(float(f["distance"]), 4),
                    "route_km": round(f["metrics"]["route_km"], 1),
                    "xy": upright_points(f["route_xy"], template),
                })
                kept += 1
            print(f"  {shape}@{target_km:.0f}/{city}: {kept} routes, "
                  f"distances "
                  f"{sorted(round(o['distance'], 3) for o in out[-kept:]) if kept else '-'}"
                  f" ({time.time() - t0:.0f}s)", flush=True)
            OUT.write_text(json.dumps(out))

    d = np.array([o["distance"] for o in out])
    print(f"\n{len(out)} routes, distance {d.min():.3f}-{d.max():.3f}")
    for lo, hi in ((0, .08), (.08, .12), (.12, .18), (.18, .25), (.25, 9)):
        print(f"  {lo:.2f}-{hi if hi < 9 else 1:.2f}: {int(((d >= lo) & (d < hi)).sum())}")
    print(f"wrote {OUT.name} ({OUT.stat().st_size / 1000:.0f} KB)")


if __name__ == "__main__":
    main()
