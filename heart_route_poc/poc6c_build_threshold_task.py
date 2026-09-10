"""
POC 6 - the third rater asks a question nobody has asked yet.

Two raters have now answered the tilt question identically: 18 rotated-vs-upright
pairs across four shapes, every one called "about the same", by people who were
demonstrably discriminating (4/4 anchors) and self-consistent (4/4 repeats).
Asking a third person the same thing would buy very little.

The genuinely untested question is the one the metric is actually USED for.
Every human judgement so far has been about tilt (ties) or about a defining
feature being destroyed (obvious). Nobody has ever been asked to rank two REAL
routes of differing quality - which is the only thing the location search does
with the metric. If people cannot tell a 0.06 route from a 0.09 one, then the
search's fine-grained ranking is optimising something invisible, and effort
should go to route length or safety instead once a shape is recognisable.

So this measures a DISCRIMINATION THRESHOLD: how big a gap in the metric has to
be before a person can see it.

Precision comes from a controlled ladder rather than found examples. The best
real heart route is degraded with smooth low-frequency noise at rising
amplitudes, giving rungs whose metric distances are known exactly, and pairs are
drawn to span gaps from negligible to obvious. Catch trials pair two rungs of
EQUAL amplitude (different noise seeds): a rater who calls those different is
guessing, which sets the floor for reading everything else.

Run:  python poc6c_build_threshold_task.py
Out:  poc6c_threshold_task.html, poc6c_ladder.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

from heart_route_poc import download_walk_graph
from heart_route_poc3 import NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON
from heart_route_poc4 import smooth_noise
from poc5_build_pairs import to_svg_path
from poc6_shapes import WIDTH_M, refine
from shape_library import resample_by_arclength
from heart_route_poc3 import place_shape
from shape_metrics import shape_distance

RESULTS = Path(__file__).with_name("poc6_results.json")
OUT_HTML = Path(__file__).with_name("poc6c_threshold_task.html")
OUT_LADDER = Path(__file__).with_name("poc6c_ladder.json")
TEMPLATE_PAGE = Path(__file__).with_name("poc5_build_page.py")

SHAPE = "heart"
AMPLITUDES = [0, 10, 20, 30, 45, 60, 90, 130, 200]
# Gaps to probe, in metric units. Weighted heavily toward the small end:
# POC 6's search shortlists spanned only 0.046 to 0.17, so whether a person
# can see a 0.02 gap decides whether the search's ranking means anything.
TARGET_GAPS = [0.0, 0.0, 0.0, 0.010, 0.020, 0.030, 0.040, 0.055,
               0.075, 0.100, 0.150, 0.220, 0.320]
SEED = 6060


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

    # The ladder. Two seeds per amplitude so equal-quality catch pairs exist.
    rungs = {}
    for amplitude in AMPLITUDES:
        for seed in (1, 2):
            key = f"a{amplitude}_s{seed}"
            curve = base if amplitude == 0 else smooth_noise(base, amplitude, seed=seed)
            rungs[key] = {"xy": curve, "amplitude": amplitude, "seed": seed,
                          "distance": shape_distance(curve, template)}

    print(f"{'rung':<12}{'amplitude':>11}{'distance':>11}")
    for key, rung in rungs.items():
        print(f"{key:<12}{rung['amplitude']:>10} m{rung['distance']:>11.4f}")

    # Choose, for each target gap, the untaken rung pair whose actual gap is
    # closest to it. Equal-amplitude pairs are the catch trials and are reserved
    # for the zero targets, so a "gap" trial is never secretly a catch trial.
    keys = list(rungs)
    catches = [(a, b) for i, a in enumerate(keys) for b in keys[i + 1:]
               if rungs[a]["amplitude"] == rungs[b]["amplitude"]]
    gaps_pool = [(a, b) for i, a in enumerate(keys) for b in keys[i + 1:]
                 if rungs[a]["amplitude"] != rungs[b]["amplitude"]]

    trials, used = [], set()
    for target in TARGET_GAPS:
        pool = catches if target == 0.0 else gaps_pool
        available = [p for p in pool if p not in used]
        if not available:
            continue
        pair = min(available,
                   key=lambda p: abs(abs(rungs[p[0]]["distance"] - rungs[p[1]]["distance"]) - target))
        used.add(pair)
        gap = abs(rungs[pair[0]]["distance"] - rungs[pair[1]]["distance"])
        trials.append({"pair_id": f"g{len(trials):02d}", "items": list(pair),
                       "kind": "catch" if target == 0.0 else "gap",
                       "gap": round(gap, 4), "repeat_of": None})

    rng = np.random.default_rng(SEED)
    gaps = [t for t in trials if t["kind"] == "gap"]
    for pick in rng.choice(len(gaps), 2, replace=False):
        source = gaps[pick]
        trials.append({**source, "pair_id": f"g{len(trials):02d}",
                       "items": list(source["items"]), "repeat_of": source["pair_id"]})

    order = rng.permutation(len(trials))
    trials = [trials[i] for i in order]
    for trial in trials:
        if rng.random() < 0.5:
            trial["items"] = trial["items"][::-1]

    shapes_svg = {key: to_svg_path(rung["xy"]) for key, rung in rungs.items()}
    OUT_LADDER.write_text(json.dumps(
        {"rungs": {k: {"amplitude": v["amplitude"], "seed": v["seed"],
                       "distance": v["distance"]} for k, v in rungs.items()},
         "trials": trials}, indent=1))

    payload = json.dumps({"shapes": shapes_svg, "trials": trials}, separators=(",", ":"))
    page = TEMPLATE_PAGE.read_text().split('PAGE = """', 1)[1].rsplit('"""', 1)[0]
    page = page.replace("<title>Which One Reads As A Heart</title>",
                        "<title>How Close Is Close Enough</title>")
    page = page.replace("心形路線 · 人工判斷", "心形路線 · 品質辨別")
    page = page.replace("哪一條路線比較像心形？", "哪一條比較像心形？")
    page = page.replace(
        "兩張圖都是真實或變形過的走路路線，已經把位置和大小正規化。憑第一眼直覺選就好。"
        "鍵盤：<b>←</b> 選左、<b>→</b> 選右、<b>空白鍵</b> 差不多。",
        "兩張都是台北真實街道上的心形路線，只是貼合程度不同。位置和大小已正規化。"
        "<b>憑第一眼直覺</b>選就好。鍵盤：<b>←</b> 選左、<b>→</b> 選右。「差不多」請用滑鼠點。")
    page = page.replace(
        "這 25 題裡有幾題會重複出現，那是用來量你自己判斷的一致性 —— 沒有這個數字，"
        "就無法分辨「指標不準」和「人本來就會前後不一」。左右邊也是隨機排的。",
        "這一輪要找的是<b>「差多少才看得出來」</b>：有些題目兩張差很多，有些幾乎一樣。"
        "<b>看不出差別就請放心點「差不多」</b> —— 那正是我們要測的東西，不是答錯。"
        "其中有幾題兩張的品質其實完全相同，那是用來確認辨別下限的。")
    page = page.replace('else if (e.key === " ") { e.preventDefault(); choose("tie"); }', "")
    page = page.replace('setTimeout(function () { index++; render(); }, which === "tie" ? 0 : 160);',
                        "setTimeout(function () { index++; render(); }, 160);")
    page = page.replace('var answers = {}, index = 0, db = null, locked = false;',
                        'var answers = {}, index = 0, db = null, locked = false, shownAt = Date.now();\n'
                        '  var rater = (window.prompt("請輸入你的名字或代號（用來區分不同標註者）：") || "anon")\n'
                        '      .replace(/[^A-Za-z0-9_\\-]/g, "").slice(0, 24) || "anon";')
    page = page.replace('el.left.dataset.chosen = "0"; el.right.dataset.chosen = "0";',
                        'el.left.dataset.chosen = "0"; el.right.dataset.chosen = "0"; shownAt = Date.now();')
    page = page.replace('chose: picked, repeat_of: t.repeat_of, at: new Date().toISOString()',
                        'chose: picked, repeat_of: t.repeat_of, at: new Date().toISOString(),\n'
                        '      ms: Date.now() - shownAt, rater: rater, kind: t.kind, gap: t.gap')
    page = page.replace('db.doc("labels/" + t.pair_id)', 'db.doc("responses/" + rater + "_" + t.pair_id)')
    page = page.replace('db.collection("labels").get()', 'db.collection("responses").get()')
    page = page.replace('snap.docs.forEach(function (d) { if (d.exists) answers[d.id] = d.data(); });',
                        'snap.docs.forEach(function (d) {\n'
                        '          var v = d.data();\n'
                        '          if (d.exists && v && v.rater === rater) answers[v.pair_id] = v;\n'
                        '        });')
    page = page.replace("這是這個專案第一次有真正的 ground truth。",
                        "這一輪測的是「指標差多少，人才看得出來」。")
    OUT_HTML.write_text(page.replace("__PAYLOAD__", payload.replace("</", "<\\/")))

    print(f"\n{len(trials)} trials "
          f"({sum(1 for t in trials if t['kind'] == 'gap')} gap, "
          f"{sum(1 for t in trials if t['kind'] == 'catch')} catch, 2 repeat)")
    print("gaps: " + ", ".join(f"{t['gap']:.3f}" for t in sorted(trials, key=lambda x: x["gap"])))
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
