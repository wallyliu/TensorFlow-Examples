"""
Blind identification stimuli for the fifteen shapes in the pack.

BACKLOG #24 says it plainly: every shape in the pack passed describe.check()
and the first person to look at them rejected seven. Those seven were then
redrawn, and every judgement in that loop - mine and theirs - was made KNOWING
what the shape was supposed to be. POC 28/29 measured how far apart that is
from the question a rider actually faces, and it is not a small gap.

So this is the same task POC 28 ran on the original five, pointed at the new
pack. A rater sees one route, alone, with no reference and no label, and names
it from every shape at once plus "cannot tell". Chance is 1/(k+1).

Three things come out of one task:

  WHICH SHAPES ARE NOT RECOGNISABLE AT ALL. The cat that read as Pikachu passed
  every mechanical check there is; only a person looking at it cold finds the
  next one.

  A THRESHOLD PER SHAPE. All twelve pack shapes currently borrow the pooled
  0.201 from recognition.py, which was measured on five shapes whose identity
  is their gross outline. Applying it to a gear is using the wrong ruler.

  CAT vs CAT_HEAD. They ship as separate shapes because nobody knows which is
  more recognisable, and the person who drew them is the last one who should
  decide.

Design follows POC 28 exactly and for its reasons: every candidate placement is
kept rather than the winner alone, so the hard stimuli are real fitted routes
and not synthetic damage (POC 13: damage and noise of equal metric distance are
not equally damaging). Routes are shown upright and normalised, so neither
mental rotation nor size carries information.

Rotation is swept, unlike POC 28, which pinned it at 0. Pinning it handicaps
the search relative to the service a rider actually uses, and a handicapped
stimulus answers the wrong question - "is this drawing recognisable" becomes
"is this drawing recognisable when badly placed".

One network for the whole run. POC 28 reloaded per configuration and paid 25s
each time; a single 12 km half-box in Taipei holds every shape here at these
sizes, so it is loaded once.

Run:  python -m experiments.poc32_pack_stimuli
Out:  results/poc32_stimuli.json
"""

from __future__ import annotations

import json
import time

import numpy as np
from pyproj import Transformer

import routeshape.feasibility as rf
import routeshape.shapes.pack as pack
import routeshape.street_scale as ss
from routeshape.matching import NoRouteFoundError
from routeshape.paths import RESULTS
from routeshape.placement import (GRID_STEP_M, MIN_SEPARATION_M, build_center_grid,
                                  build_street_index, place_shape, select_candidates)
from routeshape.region.graph import region_graph
from routeshape.search import ROTATIONS_DEG, coarse_scan, refine
from routeshape.shapes.library import resample_by_arclength
from routeshape.metrics import alignment_angle

MODE = "bike"
CITY, LAT, LON = "台北", 25.0400, 121.5400
HALF_M = 12000.0
CANDIDATES = 6
# Comfortably above each shape's own floor, capped so one network holds them
# all. Not the smallest that works: the question here is whether the DRAWING
# reads, and a shape starved of size answers a different one.
def target_for(floor_km: float) -> float:
    return float(min(40.0, max(20.0, floor_km * 1.5)))

OUT = RESULTS / "poc32_stimuli.json"


def upright_points(route_xy, template, n=220) -> list:
    """The route turned upright and normalised, as a short point array."""
    angle = np.radians(alignment_angle(route_xy, template))
    rot = np.array([[np.cos(angle), -np.sin(angle)],
                    [np.sin(angle), np.cos(angle)]])
    xy = (route_xy - route_xy.mean(axis=0)) @ rot.T
    span = float(np.abs(xy).max())
    xy = xy / span if span > 0 else xy
    if len(xy) > n:
        xy = xy[np.linspace(0, len(xy) - 1, n).round().astype(int)]
    return [[round(float(a), 4), round(float(b), 4)] for a, b in xy]


def main() -> None:
    names = pack.install()
    scale = ss.scale_for(LAT, LON, MODE, rf.MODES[MODE]["street_scale_m"])
    print(f"street scale {scale:.0f} m; loading one {HALF_M / 1000:.0f} km network")
    t0 = time.time()
    graph = region_graph(LAT, LON, HALF_M, mode=MODE)
    tree = build_street_index(graph)
    to_xy = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    region = np.array(to_xy.transform(LON, LAT))
    print(f"  {graph.number_of_nodes():,} nodes in {time.time() - t0:.0f}s")

    out = []
    for shape in names:
        floor = rf.min_distance_km(shape, MODE, scale)
        target_km = target_for(floor)
        plan = rf.plan(shape, target_km, MODE, scale)
        if not plan.feasible:
            print(f"  {shape}: {plan.reason}", flush=True)
            continue
        width_m, points = float(plan.width_m), int(plan.points)
        if width_m * 1.0 > HALF_M:
            print(f"  {shape}: {width_m:.0f} m wider than the box", flush=True)
            continue
        dense = resample_by_arclength(shape, 4000)
        closed = np.vstack([dense, dense[:1]])
        centers, _, _ = build_center_grid(
            region, max(400.0, HALF_M - width_m * 0.75), GRID_STEP_M)
        # Sweep rotation, as the service does. POC 28 pinned it at 0 and the
        # stimuli that came out were systematically worse than what a rider
        # would actually be given - cat_head's best fit went 0.036 -> 0.075 -
        # which would have been read as "the drawing is poor" rather than "the
        # search was handicapped". The rotations cost nothing: the scan is
        # cheap and the same six placements get refined either way.
        scored = coarse_scan(tree, centers, shape, width_m, ROTATIONS_DEG)
        if not np.isfinite(scored["score"]).any():
            print(f"  {shape}: no placement", flush=True)
            continue
        t1, kept = time.time(), []
        for row in select_candidates(scored, CANDIDATES, MIN_SEPARATION_M):
            centre = np.array([row["x"], row["y"]])
            try:
                fit = refine(graph, shape, centre, row["rotation"], width_m,
                             points=points)
            except NoRouteFoundError:
                fit = None
            if fit is None:
                continue
            template = place_shape(closed, centre, width_m, 0.0)
            kept.append({
                "shape": shape, "city": CITY, "target_km": target_km,
                "floor_km": round(floor, 1), "width_m": round(width_m),
                "points": points,
                "distance": round(float(fit["distance"]), 4),
                "route_km": round(fit["metrics"]["route_km"], 1),
                "xy": upright_points(fit["route_xy"], template),
            })
        out.extend(kept)
        print(f"  {shape:10s} floor {floor:4.1f} -> {target_km:4.1f} km, "
              f"{len(kept)} routes, "
              f"{sorted(round(k['distance'], 3) for k in kept)} "
              f"({time.time() - t1:.0f}s)", flush=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False))

    d = np.array([o["distance"] for o in out])
    print(f"\n{len(out)} routes over {len(set(o['shape'] for o in out))} shapes, "
          f"distance {d.min():.3f}-{d.max():.3f}")
    for lo, hi in ((0, .08), (.08, .12), (.12, .18), (.18, .25), (.25, 9)):
        print(f"  {lo:.2f}-{hi if hi < 9 else 1:.2f}: "
              f"{int(((d >= lo) & (d < hi)).sum())}")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1000:.0f} KB)")


if __name__ == "__main__":
    main()
