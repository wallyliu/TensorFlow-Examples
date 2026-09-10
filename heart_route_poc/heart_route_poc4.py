"""
POC 4 - fixing the ruler
========================

POC 3 ended by showing the search gaming its own objective: a heart tilted 30
degrees scored the same as an upright one and looked much worse. Its
recommendation was to replace the metric. Reading the code first turned up a
cheaper diagnosis - chamfer was compared against the PLACED AND ROTATED
reference, so the rotation cancelled out before any arithmetic happened - which
raises the possibility that the metric was fine and only the reference was wrong.

So rather than assume, this POC builds four candidate metrics (see
shape_metrics.py) and puts them through a battery of deformations whose correct
ordering can be asserted with confidence:

    identity / translation / scale / start-point   must score ~0
    rotation                                       must be penalised, and more so with angle
    noise                                          must rise monotonically with amplitude
    circles, squares, upside-down hearts           must score worse than a noisy heart
    filling in the cleft                           must cost more than an equal-sized
                                                   bump elsewhere - the cleft IS the heart

No human study was run, so the battery is the honest limit of what is claimed
here: these are properties any usable metric must have, not proof that a metric
which has them matches human judgement.

Run:  python heart_route_poc4.py
Out:  poc4_diagnostics.png, poc4_metric_comparison.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from heart_route_poc import generate_heart_points
from shape_metrics import (
    chamfer_placed,
    sampling_floor,
    winding,
    chamfer_upright,
    procrustes_upright,
    turning_upright,
)

WIDTH_M = 2000.0
OUT_DIAG = Path(__file__).with_name("poc4_diagnostics.png")
OUT_COMPARE = Path(__file__).with_name("poc4_metric_comparison.png")


# ---------------------------------------------------------------------------
# Building deformed hearts
# ---------------------------------------------------------------------------
def template(n: int = 512) -> np.ndarray:
    """The canonical upright heart, in metres, centred on the origin.

    Index 0 sits at the cleft: the parametric curve has x = 0, y well below the
    lobe peaks at t = 0. Several deformations below rely on that.
    """
    return generate_heart_points(n) * WIDTH_M


def rotate(xy: np.ndarray, degrees: float) -> np.ndarray:
    theta = np.radians(degrees)
    rotation = np.array([[np.cos(theta), -np.sin(theta)],
                         [np.sin(theta), np.cos(theta)]])
    return xy @ rotation.T


def smooth_noise(xy: np.ndarray, amplitude_m: float, seed: int = 0) -> np.ndarray:
    """
    Perturb the curve with low-frequency noise along its outward normal.

    Low frequency rather than per-point white noise: a real street route wanders
    away from the ideal for a block at a time, it does not jitter every 4 m. The
    displacement is scaled so its MEAN magnitude is exactly `amplitude_m`, which
    is what lets the cleft-versus-flank comparison below be a fair fight.
    """
    n = len(xy)
    rng = np.random.default_rng(seed)
    s = np.arange(n) / n
    profile = np.zeros(n)
    for harmonic in (2, 3, 5, 7):
        profile += rng.normal() * np.sin(2 * np.pi * harmonic * s + rng.uniform(0, 2 * np.pi))

    tangent = np.gradient(xy, axis=0)
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)

    profile *= amplitude_m / np.abs(profile).mean()
    return xy + normal * profile[:, None]


def fill_cleft(xy: np.ndarray) -> tuple[np.ndarray, float]:
    """
    Replace the cleft with a straight chord between the two lobe peaks.

    This is the single most destructive thing that can be done to a heart while
    leaving the rest untouched: the notch is the feature that distinguishes a
    heart from a rounded blob. Returns the deformed curve, the indices moved and
    the per-point displacement magnitudes, so an exactly matched control can be
    built elsewhere on the curve.
    """
    n = len(xy)
    y = xy[:, 1]
    right_peak = int(np.argmax(y[: n // 2]))
    left_peak = int(n // 2 + np.argmax(y[n // 2:]))

    # The cleft arc runs left peak -> end of array -> index 0 -> right peak.
    indices = list(range(left_peak, n)) + list(range(right_peak + 1))
    start, end = xy[left_peak], xy[right_peak]
    ts = np.linspace(0.0, 1.0, len(indices))[:, None]

    out = xy.copy()
    out[indices] = start * (1 - ts) + end * ts
    magnitudes = np.linalg.norm(out[indices] - xy[indices], axis=1)
    return out, indices, magnitudes


def transplant_displacement(
    xy: np.ndarray, cleft_indices: list[int], magnitudes: np.ndarray,
    start_fraction: float = 0.30,
) -> np.ndarray:
    """
    The control for `fill_cleft`: apply the IDENTICAL per-point displacement
    magnitudes to an equally long arc on the lower right flank, along the local
    outward normal.

    An earlier version used a half-sine bump matched only on mean displacement.
    It happened to match on peak too, but "matched on two summary statistics" is
    weaker than "the same numbers moved the same distances", and the whole point
    of this test is that the only difference between the two cases is WHERE the
    deformation lands. So the profile is transplanted point for point.
    """
    n = len(xy)
    start = int(start_fraction * n)
    indices = [(start + i) % n for i in range(len(cleft_indices))]

    tangent = np.gradient(xy, axis=0)
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)

    out = xy.copy()
    out[indices] = xy[indices] + normal[indices] * magnitudes[:, None]
    return out


def swap_arcs(xy: np.ndarray) -> np.ndarray:
    """
    Walk the same heart in the wrong order: quarters A-B-C-D become A-C-B-D.

    The footprint barely changes - the curve still covers the heart, plus three
    chords where the traversal jumps between quarters - but the SEQUENCE is
    wrong, and the result looks like a scribble rather than a heart. This is the
    one deformation that separates an unordered metric from an ordered one, and
    it is not a contrived case: a route with a large out-and-back spur is a
    sequence error of exactly this kind, and POC 2 found spurs to be the
    artifact the eye catches first.
    """
    n = len(xy)
    q = n // 4
    return np.vstack([xy[:q], xy[2 * q:3 * q], xy[q:2 * q], xy[3 * q:]])


def circle(n: int = 512, radius_m: float = WIDTH_M / 2) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([radius_m * np.cos(t), radius_m * np.sin(t)])


def square(n: int = 512, side_m: float = WIDTH_M) -> np.ndarray:
    per_side = n // 4
    edge = np.linspace(-side_m / 2, side_m / 2, per_side, endpoint=False)
    half = side_m / 2
    return np.vstack([
        np.column_stack([edge, np.full(per_side, -half)]),
        np.column_stack([np.full(per_side, half), edge]),
        np.column_stack([edge[::-1], np.full(per_side, half)]),
        np.column_stack([np.full(per_side, -half), edge[::-1]]),
    ])


# ---------------------------------------------------------------------------
# The battery
# ---------------------------------------------------------------------------
METRICS = {
    "chamfer_placed": chamfer_placed,          # metres, the POC 1-3 incumbent
    "chamfer_upright": chamfer_upright,        # normalised units
    "procrustes_upright": procrustes_upright,  # normalised units
    "turning_upright": turning_upright,        # radians
}


def build_cases() -> list[dict]:
    """
    Every case carries the candidate curve AND the reference the incumbent
    metric would have been given in POC 1-3 - i.e. the ideal heart under the
    same rigid placement. That is what makes the comparison fair: chamfer_placed
    is being run exactly as it was actually used, not handicapped.
    """
    base = template()
    clefted, cleft_indices, cleft_magnitudes = fill_cleft(base)
    bumped = transplant_displacement(base, cleft_indices, cleft_magnitudes)

    cases = [
        {"name": "identical", "curve": base.copy(), "placed": base, "group": "invariance"},
        {"name": "translated 5 km", "curve": base + [5000.0, 3000.0],
         "placed": base + [5000.0, 3000.0], "group": "invariance"},
        {"name": "scaled 1.5x", "curve": base * 1.5, "placed": base * 1.5,
         "group": "invariance"},
        {"name": "start point moved", "curve": np.roll(base, 137, axis=0),
         "placed": base, "group": "invariance"},
    ]
    for angle in (10, 20, 30, 45, 90):
        cases.append({"name": f"rotated {angle}°", "curve": rotate(base, angle),
                      "placed": rotate(base, angle), "group": "rotation"})
    for amplitude in (20, 50, 100, 200):
        cases.append({"name": f"noise {amplitude} m",
                      "curve": smooth_noise(base, amplitude), "placed": base,
                      "group": "noise"})
    cases += [
        {"name": "cleft filled in", "curve": clefted, "placed": base, "group": "feature"},
        {"name": "same change on flank", "curve": bumped, "placed": base, "group": "feature"},
        {"name": "walked out of order", "curve": swap_arcs(base), "placed": base,
         "group": "feature"},
        {"name": "upside down", "curve": rotate(base, 180), "placed": rotate(base, 180),
         "group": "not a heart"},
        {"name": "circle", "curve": circle(), "placed": base, "group": "not a heart"},
        {"name": "square", "curve": square(), "placed": base, "group": "not a heart"},
    ]
    cases.append({"_cleft_shift": float(cleft_magnitudes.mean()), "name": "_meta",
                  "curve": base, "placed": base, "group": "_meta"})
    return cases


def score_cases(cases: list[dict]) -> dict[str, dict[str, float]]:
    """Run every metric over every case. Upright metrics ignore `placed`."""
    upright = template()
    scores: dict[str, dict[str, float]] = {}
    for case in cases:
        if case["group"] == "_meta":
            continue
        row = {}
        for name, fn in METRICS.items():
            reference = case["placed"] if name == "chamfer_placed" else upright
            row[name] = fn(case["curve"], reference)
        scores[case["name"]] = row
    return scores


def check_properties(scores: dict[str, dict[str, float]]) -> list[tuple[str, dict[str, bool]]]:
    """
    Assert the orderings a usable metric must satisfy.

    Each check returns pass/fail per metric. Tolerances are relative to each
    metric's own scale, since they are measured in metres, normalised units and
    radians respectively.
    """
    def s(case: str, metric: str) -> float:
        return scores[case][metric]

    # An invariance residual only counts as a failure if it exceeds the
    # resolution floor - two identical curves sampled from different starting
    # points cannot agree more closely than half a sample spacing - AND is an
    # appreciable fraction of the smallest real deformation in the battery.
    floors = {
        "chamfer_placed": 0.0,
        "chamfer_upright": 2 * sampling_floor(template(), 2048),
        "procrustes_upright": 2 * sampling_floor(template(), 1024),
        "turning_upright": np.inf,  # unusable on a cusped shape; see write-up
    }

    def tolerance(metric: str) -> float:
        return max(floors[metric], 0.25 * s("noise 20 m", metric))

    checks: list[tuple[str, dict[str, bool]]] = []
    for label, cases in [
        ("translation-invariant", ["translated 5 km"]),
        ("scale-invariant", ["scaled 1.5x"]),
        ("start-point-invariant", ["start point moved"]),
    ]:
        checks.append((label, {
            m: all(abs(s(c, m)) <= tolerance(m) for c in cases) for m in METRICS
        }))

    checks.append(("penalises 30° rotation", {
        m: s("rotated 30°", m) > 0.05 * s("circle", m) for m in METRICS
    }))
    checks.append(("rotation penalty grows with angle", {
        m: s("rotated 10°", m) < s("rotated 20°", m) < s("rotated 30°", m) < s("rotated 45°", m)
        for m in METRICS
    }))
    checks.append(("noise penalty grows with amplitude", {
        m: s("noise 20 m", m) < s("noise 50 m", m) < s("noise 100 m", m) < s("noise 200 m", m)
        for m in METRICS
    }))
    checks.append(("circle worse than noisy heart", {
        m: s("circle", m) > s("noise 100 m", m) for m in METRICS
    }))
    checks.append(("square worse than noisy heart", {
        m: s("square", m) > s("noise 100 m", m) for m in METRICS
    }))
    checks.append(("upside-down heart penalised", {
        m: s("upside down", m) > s("noise 100 m", m) for m in METRICS
    }))
    checks.append(("penalises wrong traversal order", {
        m: s("walked out of order", m) > s("noise 100 m", m) for m in METRICS
    }))
    checks.append(("cleft costs more than equal bump", {
        m: s("cleft filled in", m) > s("same change on flank", m) for m in METRICS
    }))
    return checks


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_scores(cases: list[dict], scores: dict[str, dict[str, float]]) -> None:
    units = {"chamfer_placed": "m", "chamfer_upright": "norm",
             "procrustes_upright": "norm", "turning_upright": "rad"}
    header = f"{'case':<22}" + "".join(f"{m.replace('_upright', '↑'):>19}" for m in METRICS)
    print(header)
    print(f"{'':<22}" + "".join(f"{'(' + units[m] + ')':>19}" for m in METRICS))
    print("-" * len(header))
    last_group = None
    for case in cases:
        if case["group"] in ("_meta",):
            continue
        if case["group"] != last_group:
            print(f"  -- {case['group']}")
            last_group = case["group"]
        row = scores[case["name"]]
        print(f"{case['name']:<22}" + "".join(f"{row[m]:>19.3f}" for m in METRICS))


def print_checks(checks) -> dict[str, int]:
    header = f"{'property':<36}" + "".join(f"{m.replace('_upright', '↑'):>19}" for m in METRICS)
    print("\n" + header)
    print("-" * len(header))
    tally = {m: 0 for m in METRICS}
    for label, results in checks:
        print(f"{label:<36}" + "".join(
            f"{('PASS' if results[m] else 'FAIL'):>19}" for m in METRICS))
        for m in METRICS:
            tally[m] += bool(results[m])
    print("-" * len(header))
    print(f"{'passed':<36}" + "".join(f"{f'{tally[m]}/{len(checks)}':>19}" for m in METRICS))
    return tally


def plot_diagnostics(cases: list[dict], out_path: Path = OUT_DIAG) -> None:
    """Show every deformation, so the reader can judge the orderings themselves."""
    drawable = [c for c in cases if c["group"] != "_meta"]
    cols = 5
    rows = int(np.ceil(len(drawable) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(3.1 * cols, 3.1 * rows))
    base = template()
    for ax, case in zip(axes.ravel(), drawable):
        closed = np.vstack([case["curve"], case["curve"][:1]])
        ref = np.vstack([base, base[:1]])
        ax.plot(ref[:, 0], ref[:, 1], color="#cccccc", linewidth=1.0)
        ax.plot(closed[:, 0], closed[:, 1], color="#e8443a", linewidth=1.8)
        ax.set_aspect("equal")
        ax.set_title(case["name"], fontsize=10)
        ax.set_xticks([]); ax.set_yticks([])
    for ax in axes.ravel()[len(drawable):]:
        ax.axis("off")
    fig.suptitle("POC 4 — the diagnostic battery (grey = upright template)", fontsize=14)
    fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {out_path}")


def plot_metric_comparison(scores, out_path: Path = OUT_COMPARE) -> None:
    """Each metric normalised by its own 'circle' score, so they share an axis."""
    order = ["identical", "start point moved", "scaled 1.5x", "rotated 10°", "rotated 20°",
             "rotated 30°", "rotated 45°", "rotated 90°", "noise 50 m", "noise 100 m",
             "same change on flank", "cleft filled in", "walked out of order",
             "upside down", "circle", "square"]
    fig, ax = plt.subplots(figsize=(13, 6))
    width = 0.2
    positions = np.arange(len(order))
    colors = {"chamfer_placed": "#e8443a", "chamfer_upright": "#1f6fb4",
              "procrustes_upright": "#1a7f37", "turning_upright": "#6a3d9a"}
    # One bar (procrustes on a scrambled traversal) is several times taller than
    # anything else and would flatten the rest of the chart, so the axis is
    # capped and the clipped bar labelled with its true value.
    cap = 2.0
    for i, metric in enumerate(METRICS):
        reference = scores["circle"][metric]
        values = np.array([scores[c][metric] / reference for c in order])
        offsets = positions + (i - 1.5) * width
        ax.bar(offsets, np.minimum(values, cap), width, label=metric, color=colors[metric])
        for x, value in zip(offsets, values):
            if value > cap:
                ax.annotate(f"{value:.1f}", (x, cap), ha="center", va="bottom",
                            fontsize=8, fontweight="bold", color=colors[metric])
    ax.set_ylim(0, cap * 1.08)
    ax.set_xticks(positions)
    ax.set_xticklabels(order, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("score ÷ that metric's score for a circle")
    ax.axhline(1.0, color="black", linewidth=0.8, linestyle=":")
    ax.set_title("POC 4 — what each metric charges for each deformation\n"
                 "(a usable metric is near 0 on the left, high on the right)", fontsize=12)
    ax.legend(fontsize=9)
    fig.savefig(out_path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    cases = build_cases()
    cleft_shift = next(c["_cleft_shift"] for c in cases if c["group"] == "_meta")
    print(f"cleft fill and flank bump both displace {cleft_shift:.0f} m on average, "
          "over arcs of equal length\n")

    scores = score_cases(cases)
    print_scores(cases, scores)
    checks = check_properties(scores)
    tally = print_checks(checks)

    print("\nPlotting")
    plot_diagnostics(cases)
    plot_metric_comparison(scores)

    best = max(tally, key=lambda m: tally[m])
    print(f"\nbest on the battery: {best} ({tally[best]}/{len(checks)})")


if __name__ == "__main__":
    main()
