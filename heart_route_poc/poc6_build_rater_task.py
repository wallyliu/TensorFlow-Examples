"""
POC 6 - the labelling task for a SECOND rater.

POC 5's whole conclusion - that tilt does not reduce how much a shape reads as
itself, which reversed POC 3's upright default and POC 4's metric choice - rests
on eight judgements from one person. That is thin enough that it was listed as
POC 5's first limitation. This is the replication, extended to the new shapes so
the metric is checked beyond hearts at the same time.

Two questions, nothing else:

  TILT     the same route shown twice, one copy rotated 20 or 40 degrees.
           Does rotation make a shape read less like itself?
  FEATURE  a shape with its defining feature flattened (a heart's cleft, a
           star's notch) against the SAME route with an identical displacement
           applied elsewhere. Is the defining feature special, or is a
           deformation just a deformation?

Plus anchors, whose answers are known, and repeats, which measure whether the
rater contradicts themselves - the ceiling on any agreement score.

The page asks for a name first and namespaces every answer by it, so several
people can use the same link without overwriting each other.

Run:  python poc6_build_rater_task.py
Out:  poc6_rater_task.html
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

from heart_route_poc import download_walk_graph
from heart_route_poc3 import NETWORK_HALF_SIZE_M, SEARCH_LAT, SEARCH_LON
from poc5_build_pairs import to_svg_path
from poc6_shapes import WIDTH_M, refine
from shape_metrics import resample_closed

RESULTS = Path(__file__).with_name("poc6_results.json")
OUT_HTML = Path(__file__).with_name("poc6_rater_task.html")
TEMPLATE_PAGE = Path(__file__).with_name("poc5_build_page.py")

# Where each shape's defining feature sits, as a fraction of the way around the
# ideal contour, and how much of the contour it occupies. The heart's cleft is
# at the start of its parameterisation; the star's first inner notch is one
# tenth of the way round, since its ten vertices are equally spaced by arc
# length. Shapes with no single defining feature are not feature-tested.
FEATURES = {"heart": (0.0, 0.20), "star5": (0.10, 0.10)}
ANGLES = [20, 40]
SEED = 606


def flatten_feature(route_xy, reference_xy, at_fraction, span_fraction, n=512):
    """
    Flatten one arc of a real route, and transplant the identical per-point
    displacements to an arc of the same length a quarter turn away.

    Generalised from POC 5, where it was written for the heart's cleft. Both
    deformations move the same points by the same distances; only WHERE differs,
    which is the whole question.
    """
    route = resample_closed(route_xy, n)
    ideal = resample_closed(reference_xy, n)

    span = max(4, int(span_fraction * n))
    anchor = ideal[int(at_fraction * n) % n]
    centre = int(np.argmin(np.hypot(*(route - anchor).T)))
    indices = [(centre - span // 2 + i) % n for i in range(span)]

    start, end = route[indices[0]], route[indices[-1]]
    ts = np.linspace(0.0, 1.0, len(indices))[:, None]
    flattened = route.copy()
    flattened[indices] = start * (1 - ts) + end * ts
    magnitudes = np.linalg.norm(flattened[indices] - route[indices], axis=1)

    # Smoothed normals: a street route's raw local normals swing block to block,
    # and displacing along them makes the arc cross itself, which reads as
    # broken rather than deformed.
    window = 15
    kernel = np.ones(window) / window
    smoothed = np.column_stack([
        np.convolve(np.r_[route[-window:, ax], route[:, ax], route[:window, ax]],
                    kernel, mode="same")[window:-window] for ax in (0, 1)
    ])
    tangent = np.gradient(smoothed, axis=0)
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)

    control_centre = (centre + n // 4) % n
    control_idx = [(control_centre - span // 2 + i) % n for i in range(span)]
    control = route.copy()
    control[control_idx] = route[control_idx] + normal[control_idx] * magnitudes[:, None]
    return flattened, control


def rotate(xy, degrees):
    theta = np.radians(degrees)
    r = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    centre = xy.mean(axis=0)
    return (xy - centre) @ r.T + centre


def main() -> None:
    summary = {row["shape"]: row for row in json.loads(RESULTS.read_text())}
    graph = download_walk_graph(SEARCH_LAT, SEARCH_LON, NETWORK_HALF_SIZE_M)
    to_proj = Transformer.from_crs("EPSG:4326", graph.graph["crs"], always_xy=True)
    rng = np.random.default_rng(SEED)

    shapes_svg, trials = {}, []
    for shape, row in summary.items():
        centre = np.array(to_proj.transform(row["lon"], row["lat"]))
        best = refine(graph, shape, centre, row["rotation"], WIDTH_M)
        # Un-rotate the fitted route by its placement angle so the baseline is
        # shown upright. The search is free to place a shape at any angle now,
        # but a tilt question whose "untilted" member is already at 300 degrees
        # tests nothing - both members would look equally odd.
        base = rotate(best["route_xy"], -row["rotation"])
        shapes_svg[shape] = to_svg_path(base)

        for angle in ANGLES:
            key = f"{shape}_rot{angle}"
            shapes_svg[key] = to_svg_path(rotate(base, angle))
            trials.append({"pair_id": f"q{len(trials):02d}", "items": [shape, key],
                           "kind": "tilt", "shape": shape, "repeat_of": None})

        if shape in FEATURES:
            at, span = FEATURES[shape]
            flat, ctrl = flatten_feature(
                base, rotate(best["reference"], -row["rotation"]), at, span)
            shapes_svg[f"{shape}_flat"] = to_svg_path(flat)
            shapes_svg[f"{shape}_ctrl"] = to_svg_path(ctrl)
            trials.append({"pair_id": f"q{len(trials):02d}",
                           "items": [f"{shape}_flat", f"{shape}_ctrl"],
                           "kind": "feature", "shape": shape, "repeat_of": None})
            trials.append({"pair_id": f"q{len(trials):02d}",
                           "items": [shape, f"{shape}_flat"],
                           "kind": "anchor", "shape": shape, "repeat_of": None})

    tilt = [t for t in trials if t["kind"] == "tilt"]
    for pick in rng.choice(len(tilt), 2, replace=False):
        source = tilt[pick]
        trials.append({**source, "pair_id": f"q{len(trials):02d}",
                       "items": list(source["items"]), "repeat_of": source["pair_id"]})

    order = rng.permutation(len(trials))
    trials = [trials[i] for i in order]
    for trial in trials:
        if rng.random() < 0.5:
            trial["items"] = trial["items"][::-1]

    payload = json.dumps({"shapes": shapes_svg, "trials": trials}, separators=(",", ":"))
    page = TEMPLATE_PAGE.read_text().split('PAGE = """', 1)[1].rsplit('"""', 1)[0]

    page = page.replace("<title>Which One Reads As A Heart</title>",
                        "<title>Which One Reads As The Shape</title>")
    page = page.replace("心形路線 · 人工判斷", "圖形路線 · 人工判斷")
    page = page.replace("哪一條路線比較像心形？", "哪一個形狀比較完整、比較好認？")
    page = page.replace(
        "兩張圖都是真實或變形過的走路路線，已經把位置和大小正規化。憑第一眼直覺選就好。"
        "鍵盤：<b>←</b> 選左、<b>→</b> 選右、<b>空白鍵</b> 差不多。",
        "每一張都是台北真實街道上走得出來的路線，畫的是愛心、星星、月亮或三角形。"
        "位置和大小都已正規化。<b>憑第一眼直覺選</b>就好，不用細看。"
        "鍵盤：<b>←</b> 選左、<b>→</b> 選右。「差不多」請用滑鼠點。")
    page = page.replace(
        "這 25 題裡有幾題會重複出現，那是用來量你自己判斷的一致性 —— 沒有這個數字，"
        "就無法分辨「指標不準」和「人本來就會前後不一」。左右邊也是隨機排的。",
        "有幾題會重複出現，那是用來量你自己判斷的一致性；左右邊也是隨機排的。"
        "如果兩張真的看不出差別，<b>請放心選「差不多」</b> —— 那本身就是有用的答案。")
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
                        '      ms: Date.now() - shownAt, rater: rater, kind: t.kind, shape: t.shape')
    page = page.replace('db.doc("labels/" + t.pair_id)', 'db.doc("responses/" + rater + "_" + t.pair_id)')
    page = page.replace('db.collection("labels").get()', 'db.collection("responses").get()')
    page = page.replace('snap.docs.forEach(function (d) { if (d.exists) answers[d.id] = d.data(); });',
                        'snap.docs.forEach(function (d) {\n'
                        '          var v = d.data();\n'
                        '          if (d.exists && v && v.rater === rater) answers[v.pair_id] = v;\n'
                        '        });')
    page = page.replace("這是這個專案第一次有真正的 ground truth。",
                        "這是第二位標註者的資料，用來檢驗第一位的結論站不站得住。")

    OUT_HTML.write_text(page.replace("__PAYLOAD__", payload.replace("</", "<\\/")))
    kinds = {k: sum(1 for t in trials if t["kind"] == k) for k in {t["kind"] for t in trials}}
    print(f"{len(trials)} trials: " + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())))
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
