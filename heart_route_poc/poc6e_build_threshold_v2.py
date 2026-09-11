"""
POC 6 - threshold task, version 2, after the third rater's feedback.

The rater reported that on some pairs BOTH routes looked unlike a heart, and
with only "left / right / about the same" on offer they had to answer "about the
same". That conflates two completely different things:

    "both are fine and I cannot separate them"   -> below the discrimination threshold
    "both are ruined, neither is a heart"        -> past the recognisability ceiling

My instrument could not tell them apart, which is a design flaw and the third
one this project has shipped in a labelling page. Two fixes:

  1. FOUR responses, not three. "Both look like it" and "neither looks like it"
     are now separate answers, so a tie never has to stand in for a floor
     effect - and the "neither" answers locate the ceiling, which is a product
     question in its own right ("how bad is too bad to ship?") that the previous
     design could not ask at all.

  2. EVERY comparison is anchored to the clean route. Version 1 paired arbitrary
     rungs, so some pairs had no good member at all. Here one side is always the
     undegraded route, which makes "both are ruined" structurally impossible on
     the trials that define the threshold, and makes the gap directly readable as
     "how far this rung sits from a clean heart".

It also fixes the sampling flaw I owned last round: version 1 jumped from a gap
of 0.100 to 0.150 and sampled nothing where the threshold actually sits. This
concentrates rungs there.

What survived from version 1: the bracket itself. Its lower bound came from a
pair containing the clean route (answered the same way twice) and its upper bound
from a correct choice - and the flaw can only manufacture false ties, never false
correct answers. The four contaminated trials all sat below the bracket anyway.

Run:  python poc6e_build_threshold_v2.py
Out:  poc6e_threshold_v2.html, poc6e_ladder_v2.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

from heart_route_poc import download_walk_graph
from heart_route_poc3 import NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON, place_shape
from heart_route_poc4 import smooth_noise
from poc5_build_pairs import to_svg_path
from poc6_shapes import WIDTH_M, refine
from shape_library import resample_by_arclength
from shape_metrics import shape_distance

RESULTS = Path(__file__).with_name("poc6_results.json")
OUT_HTML = Path(__file__).with_name("poc6e_threshold_v2.html")
OUT_LADDER = Path(__file__).with_name("poc6e_ladder_v2.json")
TEMPLATE_PAGE = Path(__file__).with_name("poc5_build_page.py")

SHAPE = "heart"
# Gaps to probe, measured from the clean route. Concentrated across 0.10-0.17,
# the interval version 1 bracketed but never sampled.
TARGET_GAPS = [0.02, 0.05, 0.08, 0.10, 0.11, 0.12, 0.13, 0.15, 0.17, 0.22, 0.30]
SEARCH_AMPLITUDES = list(range(0, 210, 5))
SEED = 6161


def sub(text: str, old: str, new: str) -> str:
    """String replace that refuses to no-op.

    The v2 page shipped blank on its first build because a replacement targeted
    `el.tie = ...` while the source says `tie: ...` inside an object literal. The
    replace did nothing, `el.neither` stayed undefined, and the exception aborted
    the script before it painted anything. A silent no-op is the failure mode of
    patching code as text, so every edit now asserts it matched.
    """
    if old not in text:
        msg = f"replacement target not found: {old[:70]!r}"
        raise AssertionError(msg)
    return text.replace(old, new, 1)


def rotate(xy, degrees):
    theta = np.radians(degrees)
    r = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    centre = xy.mean(axis=0)
    return (xy - centre) @ r.T + centre


def main() -> None:
    row = {r["shape"]: r for r in json.loads(RESULTS.read_text())}[SHAPE]
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    centre = np.array(to_proj.transform(row["lon"], row["lat"]))

    best = refine(graph, SHAPE, centre, row["rotation"], WIDTH_M)
    base = rotate(best["route_xy"], -row["rotation"])
    dense = resample_by_arclength(SHAPE, 4000)
    template = place_shape(np.vstack([dense, dense[:1]]), base.mean(axis=0), WIDTH_M, 0.0)

    clean = shape_distance(base, template)
    print(f"clean route sits at {clean:.4f}\n")

    # Sweep amplitudes, then pick for each target gap the amplitude landing
    # closest to it. Sweeping beats guessing amplitudes: the mapping from metres
    # of noise to metric distance is not linear and differs per route.
    sweep = {}
    for amplitude in SEARCH_AMPLITUDES:
        if amplitude == 0:
            continue
        curve = smooth_noise(base, amplitude, seed=1)
        sweep[amplitude] = shape_distance(curve, template)

    rungs = {"a0_s1": {"amplitude": 0, "seed": 1, "distance": clean, "xy": base},
             "a0_s2": {"amplitude": 0, "seed": 2, "distance": clean, "xy": base.copy()}}
    chosen_amps = []
    for target in TARGET_GAPS:
        amplitude = min((a for a in sweep if a not in chosen_amps),
                        key=lambda a: abs((sweep[a] - clean) - target))
        chosen_amps.append(amplitude)
        key = f"a{amplitude}"
        rungs[key] = {"amplitude": amplitude, "seed": 1, "distance": sweep[amplitude],
                      "xy": smooth_noise(base, amplitude, seed=1)}
        print(f"  target gap {target:.2f} -> amplitude {amplitude:>3} m, "
              f"distance {sweep[amplitude]:.4f}, actual gap {sweep[amplitude] - clean:.4f}")

    trials = []
    for amplitude in chosen_amps:
        key = f"a{amplitude}"
        trials.append({"pair_id": f"v{len(trials):02d}", "items": ["a0_s1", key],
                       "kind": "gap", "gap": round(rungs[key]["distance"] - clean, 4),
                       "repeat_of": None})
    # Catch trial: the clean route against itself.
    trials.append({"pair_id": f"v{len(trials):02d}", "items": ["a0_s1", "a0_s2"],
                   "kind": "catch", "gap": 0.0, "repeat_of": None})

    rng = np.random.default_rng(SEED)
    near = [t for t in trials if t["kind"] == "gap" and 0.09 <= t["gap"] <= 0.18]
    for pick in rng.choice(len(near), 2, replace=False):
        source = near[pick]
        trials.append({**source, "pair_id": f"v{len(trials):02d}",
                       "items": list(source["items"]), "repeat_of": source["pair_id"]})

    order = rng.permutation(len(trials))
    trials = [trials[i] for i in order]
    for trial in trials:
        if rng.random() < 0.5:
            trial["items"] = trial["items"][::-1]

    shapes_svg = {k: to_svg_path(v["xy"]) for k, v in rungs.items()}
    OUT_LADDER.write_text(json.dumps(
        {"clean": clean,
         "rungs": {k: {kk: vv for kk, vv in v.items() if kk != "xy"} for k, v in rungs.items()},
         "trials": trials}, indent=1))

    payload = json.dumps({"shapes": shapes_svg, "trials": trials}, separators=(",", ":"))
    page = TEMPLATE_PAGE.read_text().split('PAGE = """', 1)[1].rsplit('"""', 1)[0]

    page = sub(page, "<title>Which One Reads As A Heart</title>",
                        "<title>How Close Is Close Enough</title>")
    page = sub(page, "心形路線 · 人工判斷", "心形路線 · 品質辨別（修正版）")
    page = sub(page, "哪一條路線比較像心形？", "哪一條比較像心形？")
    page = sub(page, 
        "兩張圖都是真實或變形過的走路路線，已經把位置和大小正規化。憑第一眼直覺選就好。"
        "鍵盤：<b>←</b> 選左、<b>→</b> 選右、<b>空白鍵</b> 差不多。",
        "兩張都是台北真實街道上的心形路線，貼合程度不同。<b>憑第一眼直覺</b>選就好。"
        "鍵盤：<b>←</b> 選左、<b>→</b> 選右；下面兩個選項請用滑鼠點。")
    page = sub(page, 
        "這 25 題裡有幾題會重複出現，那是用來量你自己判斷的一致性 —— 沒有這個數字，"
        "就無法分辨「指標不準」和「人本來就會前後不一」。左右邊也是隨機排的。",
        "上一版只有「差不多」一個選項，害得「兩張都好，分不出來」和「兩張都不像心形」"
        "被迫擠在同一個答案裡 —— 這是我的設計疏失。這一版把兩者拆開了，"
        "<b>請照實選</b>，兩種都是有用的答案。這一輪也特別加密了最難分辨的那一段。")

    # Four responses instead of three.
    page = sub(page, 
        '<button class="tie" id="tie" type="button">兩個差不多</button>',
        '<button class="tie" id="tie" type="button">兩張都像，但分不出哪個比較像</button>\n'
        '      <button class="tie" id="neither" type="button">兩張都不像心形</button>')
    page = sub(page, '<div style="display:flex; justify-content:center; margin-top:18px">',
                        '<div style="display:flex; justify-content:center; gap:12px; '
                        'flex-wrap:wrap; margin-top:18px">')
    page = sub(page, 'else if (e.key === " ") { e.preventDefault(); choose("tie"); }', "")
    page = sub(page, 'setTimeout(function () { index++; render(); }, which === "tie" ? 0 : 160);',
                        "setTimeout(function () { index++; render(); }, 160);")
    page = sub(page, 'var picked = which === "tie" ? "tie" : t.items[which === "left" ? 0 : 1];',
                        'var picked = (which === "tie" || which === "neither") ? which\n'
                        '      : t.items[which === "left" ? 0 : 1];')
    page = sub(page, 'if (which !== "tie") document.getElementById(which).dataset.chosen = "1";',
                        'if (which === "left" || which === "right")\n'
                        '      document.getElementById(which).dataset.chosen = "1";')
    page = sub(page, '    tie: document.getElementById("tie"),',
               '    tie: document.getElementById("tie"),\n'
               '    neither: document.getElementById("neither"),')
    page = sub(page, 'el.tie.addEventListener("click", function () { choose("tie"); });',
                        'el.tie.addEventListener("click", function () { choose("tie"); });\n'
                        '  el.neither.addEventListener("click", function () { choose("neither"); });')
    page = sub(page, 'var answers = {}, index = 0, db = null, locked = false;',
                        'var answers = {}, index = 0, db = null, locked = false, shownAt = Date.now();\n'
                        '  var rater = (window.prompt("請輸入你的名字或代號：") || "anon")\n'
                        '      .replace(/[^A-Za-z0-9_\\-]/g, "").slice(0, 24) || "anon";')
    page = sub(page, 'el.left.dataset.chosen = "0"; el.right.dataset.chosen = "0";',
                        'el.left.dataset.chosen = "0"; el.right.dataset.chosen = "0"; shownAt = Date.now();')
    page = sub(page, 'chose: picked, repeat_of: t.repeat_of, at: new Date().toISOString()',
                        'chose: picked, repeat_of: t.repeat_of, at: new Date().toISOString(),\n'
                        '      ms: Date.now() - shownAt, rater: rater, kind: t.kind, gap: t.gap')
    page = sub(page, 'db.doc("labels/" + t.pair_id)', 'db.doc("v2/" + rater + "_" + t.pair_id)')
    page = sub(page, 'db.collection("labels").get()', 'db.collection("v2").get()')
    page = sub(page, 'snap.docs.forEach(function (d) { if (d.exists) answers[d.id] = d.data(); });',
                        'snap.docs.forEach(function (d) {\n'
                        '          var v = d.data();\n'
                        '          if (d.exists && v && v.rater === rater) answers[v.pair_id] = v;\n'
                        '        });')
    page = sub(page, 'var ties = vals.filter(function (a) { return a.chose === "tie"; }).length;',
                        'var ties = vals.filter(function (a) { return a.chose === "tie"; }).length;\n'
                        '    var none = vals.filter(function (a) { return a.chose === "neither"; }).length;')
    page = sub(page, "'<dt>判定差不多</dt><dd>' + ties + ' 題</dd>' +",
                        "'<dt>兩張都像</dt><dd>' + ties + ' 題</dd>' +\n"
                        "      '<dt>兩張都不像</dt><dd>' + none + ' 題</dd>' +")
    page = sub(page, "這是這個專案第一次有真正的 ground truth。",
                        "這一版把「都像但分不出來」和「都不像」拆開了，謝謝你指出上一版的問題。")

    OUT_HTML.write_text(page.replace("__PAYLOAD__", payload.replace("</", "<\\/")))
    print(f"\n{len(trials)} trials, all anchored to the clean route")
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
