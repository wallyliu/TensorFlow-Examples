"""
The constants were measured in Taipei. Outside it they are wrong, and the
feasibility check says "yes" anyway.

`route_feasibility` answers "can this shape be drawn in this distance" from two
numbers: a street scale of 280 m and a detour ratio of 1.26, both measured on
the Taipei bike network. Backlog item 5 has said since POC 9 that they are
constants from one city.

The regional cache makes this testable rather than theoretical. Asking the
service for a 10 km heart at Yilan returns "feasible - 2.5 km wide, 28 contour
points", and then finds no placement at all: the coarse scan rejects every one
because the ideal contour strays further from the network than the 250 m
admissibility gap allows. The answer was confidently wrong, which is the
failure mode this project keeps hitting and the one it is least able to notice.

This measures the street scale directly wherever the region cache reaches:
sample random points, take the distance to the nearest piece of network. The
median is what `street_scale_m` is supposed to be.

Run:  python poc22_constants.py
Out:  poc22_constants.png, poc22_constants.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

import route_feasibility as rf
from heart_route_poc3 import build_street_index
from region_graph import region_graph

HALF_SIZE_M = 6000.0
SAMPLES = 20000
PLACES = {
    "Taipei Zhongzheng": (25.036, 121.520),
    "New Taipei Banqiao": (25.011, 121.463),
    "Keelung": (25.128, 121.741),
    "Taoyuan Zhongli": (24.955, 121.225),
    "Yilan Luodong": (24.677, 121.767),
    "Yilan Toucheng": (24.856, 121.823),
}

# A random point in a covered urban area is within a couple of hundred metres
# of something rideable. If most samples are beyond the admissibility gap, the
# tiles under that point are missing rather than the streets, and reporting a
# street scale from it would be a measurement of the download's progress
# dressed up as a measurement of the city.
COVERAGE_GAP_M = 250.0
COVERAGE_MIN = 0.35
OUT_PNG = Path(__file__).with_name("poc22_constants.png")
OUT_JSON = Path(__file__).with_name("poc22_constants.json")


def main() -> None:
    rng = np.random.default_rng(0)
    taipei_scale = rf.MODES["bike"]["street_scale_m"]
    results = {}

    print(f"{'place':<20}{'nodes':>9}{'median':>10}{'p90':>8}"
          f"{'vs Taipei':>10}{'heart min':>11}")
    for label, (lat, lon) in PLACES.items():
        try:
            graph = region_graph(lat, lon, HALF_SIZE_M, mode="bike")
        except FileNotFoundError:
            print(f"{label:<20}  (region cache does not reach here yet)")
            continue
        if graph.number_of_nodes() < 50:
            print(f"{label:<20}  (too few nodes: {graph.number_of_nodes()})")
            continue
        tree = build_street_index(graph)
        to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"],
                                       always_xy=True)
        centre = np.array(to_proj.transform(lon, lat))
        pts = centre + rng.uniform(-HALF_SIZE_M * 0.8, HALF_SIZE_M * 0.8,
                                   size=(SAMPLES, 2))
        d = tree.query(pts)[0]
        median = float(np.median(d))
        p90 = float(np.percentile(d, 90))
        covered = float((d <= COVERAGE_GAP_M).mean())
        if covered < COVERAGE_MIN:
            print(f"{label:<20}{graph.number_of_nodes():>9,}{median:>9.0f}m"
                  f"{p90:>7.0f}m   only {covered:.0%} of samples near a street"
                  f" - TILES MISSING, not measured")
            results[label] = {"status": "incomplete coverage",
                              "nodes": graph.number_of_nodes(),
                              "fraction_near_street": covered}
            continue
        # street_scale_m is defined as the spacing the network can resolve, and
        # the Taipei value was derived the same way, so the ratio is the factor
        # every feasibility answer is out by here.
        ratio = median / (taipei_scale / 2)   # Taipei's own median is ~half its scale
        scale = taipei_scale * ratio
        heart_km = rf.n_min("heart") * scale * rf.MODES["bike"]["detour"] / 1000
        results[label] = {"lat": lat, "lon": lon,
                          "nodes": graph.number_of_nodes(),
                          "median_m": median, "p90_m": p90,
                          "implied_scale_m": scale,
                          "heart_min_km": heart_km}
        print(f"{label:<20}{graph.number_of_nodes():>9,}{median:>9.0f}m{p90:>7.0f}m"
              f"{ratio:>9.2f}x{heart_km:>9.1f} km")

    measured = {k: v for k, v in results.items() if "median_m" in v}
    if not measured:
        print("\nNothing measurable yet: every place is short of tiles. The "
              "region download has to finish before any of these numbers mean "
              "anything about street density rather than about coverage.")
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        return
    results_measured = measured
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    fig, ax = plt.subplots(figsize=(9, 4))
    names = list(results_measured)
    med = [results_measured[k]["median_m"] for k in names]
    p90 = [results_measured[k]["p90_m"] for k in names]
    x = np.arange(len(names))
    ax.bar(x - 0.2, med, 0.4, color="#2f5d50", label="median distance to network")
    ax.bar(x + 0.2, p90, 0.4, color="#b4622c", label="90th percentile")
    ax.axhline(rf.MODES["bike"]["street_scale_m"] / 2, color="#9aa09c", ls="--",
               lw=1, label="what Taipei's constant assumes")
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("metres", fontsize=9)
    ax.set_title("How far a random point is from a rideable street", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    ax.grid(alpha=.25, lw=.6, axis="y")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140)
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
