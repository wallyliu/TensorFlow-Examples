"""
The held-out test for the wander term.

`poc15_wiggle.py` fits one constant to four rungs of one shape. That constant
then makes a falsifiable prediction on shapes it never saw, and the three
shapes here were chosen because the prediction is DIFFERENT for each:

    heart      tie, tie, tie, feature-destroyed   - crosses the threshold
    crescent   tie at every rung                  - never crosses it
    star5      feature-destroyed at every rung    - starts past it

A rater who simply always picks one side fails two of the three. A rater who
always says "about the same" fails two of the three. Only the predicted pattern
passes, which is what makes this a test rather than a demonstration.

The catch trial is `wrecked`, not `scrambled`: a rater in round two spotted the
scrambled stimulus by the triangle its chords leave across the body, and a catch
that can be recognised by its artifact measures whether the artifact was seen.

Run:  python poc15_build_task.py
Out:  rater/v3_*.png, poc15_task.html, poc15_stimuli.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from heart_route_poc4 import smooth_noise
from poc13_build_task import PAIR_OPTIONS, TEMPLATE, data_uri
from poc13_dino_stimuli import ALPHAS, deepest_fjord, fill_span, match_noise, render
from poc15_wiggle import FEATURE, N, SCALE_M, biggest_spike
from shape_library import resample_by_arclength
from shape_metrics import shape_distance

SHAPES = {"heart": "愛心", "crescent": "月亮", "star5": "星星"}
RATER = Path(__file__).with_name("rater")
OUT_HTML = Path(__file__).with_name("poc15_task.html")
OUT_JSON = Path(__file__).with_name("poc15_stimuli.json")


def build_stimuli() -> dict:
    RATER.mkdir(exist_ok=True)
    meta = {}
    for shape in SHAPES:
        clean = resample_by_arclength(shape, N) * SCALE_M
        indices, _ = (deepest_fjord(clean) if FEATURE[shape] == "fjord"
                      else biggest_spike(clean))
        render(clean, RATER / f"v3_{shape}_clean.png")
        for k, alpha in enumerate(ALPHAS, start=1):
            merged, _ = fill_span(clean, indices, alpha)
            d = shape_distance(merged, clean)
            noisy, amp = match_noise(clean, d, seed=1)
            render(merged, RATER / f"v3_{shape}_L{k}_merged.png")
            render(noisy, RATER / f"v3_{shape}_L{k}_noise.png")
            meta[f"{shape}_L{k}"] = {"shape_distance": d, "alpha": alpha,
                                     "noise_amplitude_m": amp}
        # The catch: the same wander as every noise stimulus, four times over.
        wrecked = smooth_noise(clean, 4 * amp, 7)
        render(wrecked, RATER / f"v3_{shape}_wrecked.png")
        meta[f"{shape}_wrecked"] = {
            "shape_distance": shape_distance(wrecked, clean),
            "what": "catch trial"}
    OUT_JSON.write_text(json.dumps(meta, indent=2))
    return meta


def build_trials() -> list[dict]:
    trials = []
    for shape, label in SHAPES.items():
        prompt = f"哪一張比較像{label}？"
        trials.append({"id": f"{shape}_catch", "section": shape, "kind": "pair",
                       "a": f"v3_{shape}_clean", "b": f"v3_{shape}_wrecked",
                       "options": PAIR_OPTIONS, "prompt": prompt})
        for k in range(1, len(ALPHAS) + 1):
            trials.append({"id": f"{shape}_L{k}", "section": shape, "kind": "pair",
                           "a": f"v3_{shape}_L{k}_merged",
                           "b": f"v3_{shape}_L{k}_noise",
                           "options": PAIR_OPTIONS, "prompt": prompt})
        # One repeat per shape, for self-consistency.
        trials.append({"id": f"{shape}_L3_repeat", "section": shape, "kind": "pair",
                       "repeat_of": f"{shape}_L3",
                       "a": f"v3_{shape}_L3_merged", "b": f"v3_{shape}_L3_noise",
                       "options": PAIR_OPTIONS, "prompt": prompt})
    return trials


def main() -> None:
    build_stimuli()
    trials = build_trials()

    # Shapes are interleaved rather than blocked: a rater who sees four hearts
    # in a row starts answering the block instead of the picture.
    rng = random.Random(15)
    rng.shuffle(trials)

    names = sorted({t["a"] for t in trials} | {t["b"] for t in trials})
    images = {n: data_uri(n) for n in names}
    payload = json.dumps({"trials": trials, "images": images, "version": "v3"},
                         ensure_ascii=False, separators=(",", ":"))
    html = TEMPLATE.replace("__PAYLOAD__", payload)
    marker = "<title>這些路線看起來像什麼</title>"
    assert marker in html, "title marker moved; fix this before publishing"
    html = html.replace(marker, "<title>哪一種壞法比較難認</title>")
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUT_HTML.name}: {len(trials)} trials, {len(images)} images, "
          f"{OUT_HTML.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
