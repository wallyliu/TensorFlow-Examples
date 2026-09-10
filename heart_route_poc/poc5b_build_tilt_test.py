"""
POC 5, step 5 - a focused re-test of the one question the first run left open.

The first labelling run settled the cleft question cleanly, but on TILT - the
premise underneath both POC 3's upright constraint and POC 4's whole diagnosis
- it returned 12 ties and one judgement pointing the OTHER way. That premise has
never actually been tested on a person, so it gets a proper test here.

Three changes from the first run:

  1. Tilt is isolated. Instead of comparing a tilted route against a DIFFERENT
     upright route - where the two differ in route and orientation at once - each
     pair shows the SAME route twice, one copy rotated. Any preference is then
     about orientation and nothing else.
  2. "About the same" is a deliberate click, not a spacebar that advanced with no
     delay. In the first run 13 of 24 answers landed within 1.2 s of the previous
     one, which a zero-delay key repeat makes easy to do by accident. That was a
     flaw in my instrument, not in the rater.
  3. Reaction time is recorded per trial, so the analysis can say how long each
     judgement actually took instead of inferring it from timestamps.

Run:  python poc5b_build_tilt_test.py
Out:  poc5b_tilt_test.html
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from poc5_build_pairs import to_svg_path

POOL = Path(__file__).with_name("poc5_pool.npz")
TEMPLATE_PAGE = Path(__file__).with_name("poc5_build_page.py")
OUT_HTML = Path(__file__).with_name("poc5b_tilt_test.html")

UPRIGHT = ["real07", "real02", "real10", "real11"]   # the cleanest real hearts
ANGLES = [20, 40]
SEED = 8


def rotate(xy: np.ndarray, degrees: float) -> np.ndarray:
    theta = np.radians(degrees)
    r = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    centre = xy.mean(axis=0)
    return (xy - centre) @ r.T + centre


def main() -> None:
    pool = np.load(POOL, allow_pickle=True)
    rng = np.random.default_rng(SEED)

    shapes: dict[str, str] = {}
    trials: list[dict] = []

    for name in UPRIGHT:
        base = pool[f"{name}__xy"]
        shapes[name] = to_svg_path(base)
        for angle in ANGLES:
            tilt_id = f"{name}_rot{angle}"
            shapes[tilt_id] = to_svg_path(rotate(base, angle))
            trials.append({"pair_id": f"t{len(trials):02d}", "items": [name, tilt_id],
                           "repeat_of": None, "kind": "tilt"})

    # Anchors: a known-bad shape against a good one. If these come back wrong the
    # run says nothing about tilt either.
    shapes["cleft_filled"] = to_svg_path(pool["cleft_filled__xy"])
    for name in ("real07", "real10"):
        trials.append({"pair_id": f"t{len(trials):02d}", "items": [name, "cleft_filled"],
                       "repeat_of": None, "kind": "anchor"})

    tilt_trials = [t for t in trials if t["kind"] == "tilt"]
    for pick in rng.choice(len(tilt_trials), 2, replace=False):
        source = tilt_trials[pick]
        trials.append({"pair_id": f"t{len(trials):02d}", "items": list(source["items"]),
                       "repeat_of": source["pair_id"], "kind": source["kind"]})

    order = rng.permutation(len(trials))
    trials = [trials[i] for i in order]
    for trial in trials:
        if rng.random() < 0.5:
            trial["items"] = trial["items"][::-1]

    payload = json.dumps({"shapes": shapes, "trials": trials}, separators=(",", ":"))

    page = TEMPLATE_PAGE.read_text().split('PAGE = """', 1)[1].rsplit('"""', 1)[0]
    page = page.replace("<title>Which One Reads As A Heart</title>",
                        "<title>Does A Tilted Heart Still Read</title>")
    page = page.replace("心形路線 · 人工判斷", "心形路線 · 傾斜測試")
    page = page.replace(
        "鍵盤：<b>←</b> 選左、<b>→</b> 選右、<b>空白鍵</b> 差不多。",
        "鍵盤：<b>←</b> 選左、<b>→</b> 選右。「差不多」請用滑鼠點，這一次沒有快捷鍵。")
    page = page.replace(
        "這 25 題裡有幾題會重複出現，那是用來量你自己判斷的一致性 —— 沒有這個數字，就無法分辨「指標不準」和「人本來就會前後不一」。左右邊也是隨機排的。",
        "這一輪只問一件事：<b>傾斜會不會讓心形變得比較不像心形</b>。多數題目的兩張圖是<b>同一條路線</b>，"
        "只有其中一張被轉了角度 —— 所以差別純粹來自方向。這個前提是 POC 3 和 POC 4 的基礎，但從來沒有被真人驗證過。")
    page = page.replace('else if (e.key === " ") { e.preventDefault(); choose("tie"); }', "")
    page = page.replace('setTimeout(function () { index++; render(); }, which === "tie" ? 0 : 160);',
                        "setTimeout(function () { index++; render(); }, 160);")
    # record reaction time per trial
    page = page.replace('var answers = {}, index = 0, db = null, locked = false;',
                        'var answers = {}, index = 0, db = null, locked = false, shownAt = Date.now();')
    page = page.replace('el.left.dataset.chosen = "0"; el.right.dataset.chosen = "0";',
                        'el.left.dataset.chosen = "0"; el.right.dataset.chosen = "0"; shownAt = Date.now();')
    page = page.replace('chose: picked, repeat_of: t.repeat_of, at: new Date().toISOString()',
                        'chose: picked, repeat_of: t.repeat_of, at: new Date().toISOString(),\n'
                        '      ms: Date.now() - shownAt')
    page = page.replace("這是這個專案第一次有真正的 ground truth。",
                        "這一輪專門用來檢驗「傾斜是否重要」這個假設。")

    OUT_HTML.write_text(page.replace("__PAYLOAD__", payload.replace("</", "<\\/")))
    print(f"{len(trials)} trials ({len(tilt_trials)} tilt, 2 anchor, 2 repeat)")
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
