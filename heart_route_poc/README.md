# POC 1 — Heart Route on Real Streets (Taipei Da'an)

One question only: **can an ideal heart contour be turned into a real walkable
route on Taipei streets that still looks like a heart?**

Short answer: yes. The shape survives the snap to a street grid clearly enough
to read as a heart at map zoom.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python heart_route_poc.py                 # real OSM data (needs network)
python heart_route_poc.py --offline       # synthetic grid, no network needed
```

Useful flags: `--points`, `--width-km`, `--radius-km`, `--lat`, `--lon`, `--out`.

Outputs `heart_shape_check.png` (step 1 verification) and `heart_route_poc.png`
(network + ideal contour + snapped nodes + actual route).

## Pipeline

| Step | Function |
| --- | --- |
| 1. ideal contour | `generate_heart_points()` |
| 2. place on map | `transform_shape_to_map()` |
| 3. street network | `download_walk_graph()` / `synthetic_walk_graph()` |
| 4. snap | `snap_points_to_graph()` |
| 5. route | `build_route()` |
| 6. plot | `plot_result()` |

All geometry runs in UTM zone 51N (EPSG:32651), not degrees, so the heart keeps
its aspect ratio — a degree of longitude at 25°N is only ~0.906 of a degree of
latitude, which would otherwise squash the shape horizontally.

## Metrics

Beyond the required counts, the script reports two quality numbers:

- **detour ratio** — route length ÷ ideal contour perimeter.
- **shape deviation** — symmetric mean/p95 distance between the drawn route and
  the ideal contour. This is the metric that matters. Route length alone is
  misleading: dropping waypoints shortens the route while making the drawing
  *worse*.

## `--offline` mode

The environment this was developed in blocks all OSM hosts, so `--offline`
builds a synthetic Da'an-like grid (400 m arterials, 100 m lanes, ~40% of lane
segments missing) to exercise the full pipeline. It validates the geometry and
routing logic; it is **not** a substitute for real OSM data, and any figure it
produces is labelled `[SYNTHETIC GRID]`.

## Results (synthetic grid, 36 points, 2 km wide)

```
heart sample points      : 36
unique snapped nodes     : 36
total route distance     : 12.13 km
failed/unreachable legs  : 0
detour ratio             : 1.90x
shape deviation mean/p95 : 45 m / 135 m
```

## Scope

Deliberately excluded: LLM/image/text-to-shape input, automatic location
search, route optimization, frontend, database, APIs.
