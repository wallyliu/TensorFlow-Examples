"""
Feature destruction on the hardest shape, with a matched control.

POC 7 measured merging the dinosaur's two legs at 0.060 in shape distance -
below the ~0.10 at which POC 6's raters reliably saw a difference - while a
defining feature of the shape is simply gone. Backlog item 4. The claim has
never been put to a person, and it is the claim that decides whether the metric
can be trusted to gate its own output.

Two deformations, matched to the SAME shape distance from the clean dinosaur:

  merged   the gap between the legs filled with a chord - one feature destroyed,
           everything else untouched
  noise    low-frequency wander of an amplitude tuned to land on the same
           distance - nothing destroyed, everything slightly wrong

If the metric is adequate, a rater has no reason to prefer either. If features
are what people see, the noisy one still reads as a dinosaur and the merged one
does not.

Neither member of the pair is the clean shape. That is deliberate: POC 6's v2
task anchored every pair to a clean route, which guaranteed one good member and
so recorded zero "neither looks like it" answers (backlog item 3). Unanchored
pairs and the four-option response have never been in the same instrument.

Run:  python poc13_dino_stimuli.py
Out:  rater/dino_*.png, poc13_dino.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from heart_route_poc4 import smooth_noise, swap_arcs, transplant_displacement
from shape_library import resample_by_arclength
from shape_metrics import shape_distance

N = 512
SCALE_M = 2000.0        # so noise amplitude is in metres, as POC 4 used it
OUT_DIR = Path(__file__).with_name("rater")
OUT_JSON = Path(__file__).with_name("poc13_dino.json")
ALPHAS = (0.35, 0.55, 0.75, 1.0)   # the four rungs of the iso-distance ladder


def deepest_fjord(xy: np.ndarray, max_span: float = 0.22) -> tuple[list[int], float]:
    """
    The stretch of curve that doubles back on itself the hardest.

    POC 4 hard-coded the heart's cleft by looking for its two lobe peaks. That
    does not generalise, and the dinosaur's defining gap is between its legs,
    nowhere near a y-extremum. Defined instead as the span whose arc length most
    exceeds the straight line between its ends - which is what a notch, a cleft
    and a leg gap all are.
    """
    n = len(xy)
    closed = np.vstack([xy, xy[:1]])
    step = np.hypot(*np.diff(closed, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(step)])
    best, best_ratio = None, 0.0
    for span in range(int(0.04 * n), int(max_span * n), max(1, n // 128)):
        for i in range(0, n, max(1, n // 256)):
            j = (i + span) % n
            arc = cum[i + span] - cum[i] if i + span <= n else \
                (cum[n] - cum[i]) + cum[(i + span) - n]
            chord = float(np.hypot(*(xy[j] - xy[i])))
            if chord <= 0:
                continue
            ratio = arc / chord
            if ratio > best_ratio:
                best_ratio, best = ratio, (i, span)
    i, span = best
    return [(i + k) % n for k in range(span + 1)], best_ratio


def fill_span(xy: np.ndarray, indices: list[int], alpha: float = 1.0
              ) -> tuple[np.ndarray, np.ndarray]:
    """
    Move a span of the curve `alpha` of the way toward the straight chord.

    alpha=1 erases the feature outright; smaller values close the gap part way,
    which is what makes an iso-distance ladder possible - the same destruction
    at several magnitudes, each matched against noise of equal metric distance.
    """
    out = xy.copy()
    start, end = xy[indices[0]], xy[indices[-1]]
    t = np.linspace(0.0, 1.0, len(indices))[:, None]
    chord = start * (1 - t) + end * t
    out[indices] = xy[indices] + alpha * (chord - xy[indices])
    return out, np.linalg.norm(out[indices] - xy[indices], axis=1)


def match_noise(clean: np.ndarray, target: float, seed: int) -> tuple[np.ndarray, float]:
    """Tune the noise amplitude until it sits at the same distance as the merge."""
    lo, hi = 1.0, 400.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        d = shape_distance(smooth_noise(clean, mid, seed), clean)
        if d < target:
            lo = mid
        else:
            hi = mid
    amp = 0.5 * (lo + hi)
    return smooth_noise(clean, amp, seed), amp


def render(xy: np.ndarray, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    closed = np.vstack([xy, xy[:1]])
    ax.plot(closed[:, 0], closed[:, 1], lw=1.8, color="#1a1a1a")
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(0.03, 0.03, 0.97, 0.97)
    fig.savefig(path, dpi=110, facecolor="white")
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    clean = resample_by_arclength("trex", N) * SCALE_M

    indices, ratio = deepest_fjord(clean)
    print(f"leg gap: {len(indices)} points, arc/chord {ratio:.1f}")

    variants = {"clean": clean}
    meta = {"clean": {"distance_from_clean": 0.0, "what": "the dinosaur, untouched"}}

    # The ladder: the same feature destroyed by degrees, each level matched
    # against noise of identical metric distance. If the metric says what a
    # person sees, the two members of a level are equally dinosaur-like.
    print(f"\n{'level':>6}{'alpha':>7}{'distance':>10}{'noise amp':>11}")
    for level, (alpha, seed) in enumerate(zip(ALPHAS, (1, 1, 1, 1)), start=1):
        merged, _ = fill_span(clean, indices, alpha)
        d = shape_distance(merged, clean)
        noisy, amp = match_noise(clean, d, seed)
        variants[f"L{level}_merged"] = merged
        variants[f"L{level}_noise"] = noisy
        meta[f"L{level}_merged"] = {
            "level": level, "distance_from_clean": d, "alpha": alpha,
            "what": f"leg gap closed {alpha:.0%} of the way"}
        meta[f"L{level}_noise"] = {
            "level": level, "distance_from_clean": shape_distance(noisy, clean),
            "amplitude_m": amp, "seed": seed,
            "what": "low-frequency wander, no feature destroyed"}
        print(f"{level:6d}{alpha:7.2f}{d:10.3f}{amp:11.0f}")

    # The catch trials. `scrambled` was the first one and it leaks: traversing
    # the quarters out of order leaves straight chords across the body, and a
    # rater in round two asked why some dinosaurs "suddenly have a triangle in
    # the middle". A catch a rater can spot by its artifact measures whether
    # they noticed the artifact, not whether they were judging the shape. So
    # `wrecked` replaces it for future rounds: the same wander as every noise
    # stimulus, at four times L4's amplitude, so it is far worse without looking
    # like a different kind of picture.
    variants["scrambled"] = swap_arcs(clean)
    meta["scrambled"] = {"distance_from_clean": shape_distance(variants["scrambled"], clean),
                         "what": "quarters out of order - round 1-2 catch, leaks a triangle"}
    variants["wrecked"] = smooth_noise(clean, 4 * meta["L4_noise"]["amplitude_m"], 7)
    meta["wrecked"] = {"distance_from_clean": shape_distance(variants["wrecked"], clean),
                       "amplitude_m": 4 * meta["L4_noise"]["amplitude_m"],
                       "what": "noise far past the ladder - catch trial, same idiom"}

    # POC 4's own control, kept for comparison: the merge's displacements applied
    # point for point where no feature lives. It does NOT land at the same
    # distance (0.25 against 0.17) - the same numbers moved somewhere else cost
    # more, not less - which is itself worth a rater's eyes.
    variants["transplant"] = transplant_displacement(clean, indices,
                                                     fill_span(clean, indices)[1], 0.55)
    meta["transplant"] = {
        "distance_from_clean": shape_distance(variants["transplant"], clean),
        "what": "the merge's own displacements, applied where no feature lives"}

    for key, xy in variants.items():
        render(xy, OUT_DIR / f"dino_{key}.png")
    OUT_JSON.write_text(json.dumps(meta, indent=2))
    print(f"\nwrote {len(variants)} images to {OUT_DIR.name}/ and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
