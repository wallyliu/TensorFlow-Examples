"""
POC 9 - the feasibility page.

The rule this page exists to make visible: a shape's detail costs walking
distance, and below a shape's floor there is no good answer - only a degraded
drawing the metric cannot detect. So the check belongs BEFORE anything is drawn,
and the refusal has to carry the number ("a dinosaur needs 18 km") rather than
greying a card out.

The page is generated rather than hand-written so it always shows the same
numbers as `route_feasibility`: shape outlines, n_min and perimeters are baked in
here, and the arithmetic is the module's, restated in a few lines of JavaScript.

Run:  python poc9_build_page.py
Out:  poc9_feasibility.html
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from poc5_build_pairs import to_svg_path
from route_feasibility import (
    DETOUR_RATIO, DETOUR_UNCERTAINTY, TAIPEI_STREET_SCALE_M, WINDOW_FRACTION,
    n_min, perimeter,
)
from shape_library import SHAPES, resample_by_arclength

OUT_HTML = Path(__file__).with_name("poc9_feasibility.html")

LABELS = {"heart": "愛心", "star5": "五角星", "crescent": "月亮",
          "triangle": "三角形", "trex": "恐龍"}

PAGE = """<title>Shape Or Distance, Pick One</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@400;500&display=swap">
<style>
  :root {
    --paper: #eef1f4; --card: #ffffff; --ink: #14181d; --muted: #6b7580;
    --line: #ccd4dc; --accent: #1f6f9f; --ok: #1a7f37; --no: #b0412f;
    --ok-soft: #e4f0e7; --no-soft: #f6e6e3;
    --sans: "IBM Plex Sans", system-ui, "Noto Sans TC", sans-serif;
    --serif: "IBM Plex Serif", Georgia, "Noto Serif TC", serif;
    --mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #12161a; --card: #1a1f25; --ink: #e4e9ee; --muted: #8b959f;
      --line: #2b333b; --accent: #6db4de; --ok: #5cbd77; --no: #e08472;
      --ok-soft: #1a2a1f; --no-soft: #2c1e1b;
    }
  }
  :root[data-theme="dark"] {
    --paper: #12161a; --card: #1a1f25; --ink: #e4e9ee; --muted: #8b959f;
    --line: #2b333b; --accent: #6db4de; --ok: #5cbd77; --no: #e08472;
    --ok-soft: #1a2a1f; --no-soft: #2c1e1b;
  }
  body { background: var(--paper); color: var(--ink); font-family: var(--sans);
         line-height: 1.55; padding-block: 30px 60px; padding-left: 20px; padding-right: 20px; }
  .wrap { max-width: 940px; margin: 0 auto; display: flex; flex-direction: column; gap: 26px; }

  h1 { font-family: var(--serif); font-weight: 500; font-size: clamp(24px, 3.6vw, 34px);
       margin: 0 0 8px; text-wrap: balance; }
  .lede { margin: 0; color: var(--muted); max-width: 64ch; }
  .lede b { color: var(--ink); font-weight: 600; }

  .control { background: var(--card); border: 1px solid var(--line); border-radius: 4px;
             padding: 20px 22px; display: flex; flex-direction: column; gap: 12px; }
  .control label { font-size: 13px; color: var(--muted); letter-spacing: .03em;
                   text-transform: uppercase; }
  .readout { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
  .readout .km { font-family: var(--mono); font-size: 34px; font-weight: 500;
                 font-variant-numeric: tabular-nums; }
  .readout .budget { color: var(--muted); font-size: 14px; }
  .readout .budget b { font-family: var(--mono); color: var(--accent); font-weight: 500; }
  input[type=range] { width: 100%; accent-color: var(--accent); }
  .ticks { display: flex; justify-content: space-between; font-family: var(--mono);
           font-size: 11px; color: var(--muted); }

  .row { background: var(--card); border: 1px solid var(--line); border-radius: 4px;
         padding: 16px 18px; display: grid; grid-template-columns: 62px 1fr auto;
         gap: 18px; align-items: center; }
  .row[data-ok="0"] { background: var(--no-soft); }
  .row svg { width: 56px; height: 56px; display: block; }
  .row svg path { fill: none; stroke-width: 2.6; stroke-linejoin: round; stroke-linecap: round; }
  .row[data-ok="1"] svg path { stroke: var(--ok); }
  .row[data-ok="0"] svg path { stroke: var(--no); }
  .name { font-weight: 600; display: flex; align-items: baseline; gap: 9px; }
  .name .cost { font-family: var(--mono); font-size: 12px; color: var(--muted);
                font-weight: 400; }
  .detail { color: var(--muted); font-size: 13.5px; margin-top: 3px; }
  .detail b { color: var(--ink); font-weight: 600; font-family: var(--mono); }
  .verdict { font-family: var(--mono); font-size: 12px; padding: 4px 11px;
             border-radius: 999px; white-space: nowrap; }
  .row[data-ok="1"] .verdict { background: var(--ok-soft); color: var(--ok); }
  .row[data-ok="0"] .verdict { background: var(--card); color: var(--no);
                               border: 1px solid var(--no); }
  .meter { height: 5px; background: var(--line); border-radius: 3px; margin-top: 9px;
           position: relative; overflow: hidden; }
  .meter > i { position: absolute; inset: 0 auto 0 0; border-radius: 3px; }
  .row[data-ok="1"] .meter > i { background: var(--ok); }
  .row[data-ok="0"] .meter > i { background: var(--no); }

  .note { border-left: 2px solid var(--line); padding-left: 15px; color: var(--muted);
          font-size: 13px; max-width: 68ch; }
  .note b { color: var(--ink); font-weight: 600; }
  @media (max-width: 560px) { .row { grid-template-columns: 48px 1fr; }
                              .verdict { grid-column: 2; justify-self: start; } }
</style>

<div class="wrap">
  <div>
    <h1>圖案的細節，是用走路距離買的</h1>
    <p class="lede">在台北，街道大約每 <b>160 公尺</b>才給你一次轉向的機會。一個圖案要多少個輪廓點才認得出來，
    就決定了它至少要畫多大、你至少要走多遠。<b>先決定要走多遠，再看有哪些圖案。</b></p>
  </div>

  <div class="control">
    <label for="dist">你想走多遠</label>
    <div class="readout">
      <span class="km" id="km">8.0 km</span>
      <span class="budget">這段距離買得起 <b id="cap">—</b> 個輪廓點</span>
    </div>
    <input type="range" id="dist" min="15" max="250" value="80" step="5">
    <div class="ticks"><span>1.5 km</span><span>10 km</span><span>25 km</span></div>
  </div>

  <div id="rows" style="display:flex; flex-direction:column; gap:12px"></div>

  <p class="note" id="foot"></p>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById("data").textContent);
  var slider = document.getElementById("dist");
  var rows = document.getElementById("rows");

  function render() {
    var km = slider.value / 10;
    document.getElementById("km").textContent = km.toFixed(1) + " km";
    // What the walk affords: one contour point per street scale of route.
    var cap = Math.max(1, Math.floor(km * 1000 / (D.street * D.detour)));
    document.getElementById("cap").textContent = cap;

    var html = "";
    D.shapes.slice().sort(function (a, b) { return a.nmin - b.nmin; }).forEach(function (s) {
      var ok = s.nmin <= cap;
      var width = km * 1000 / (s.perimeter * D.detour);
      var n = Math.max(s.nmin, Math.round(D.fraction * cap));
      var lo = (km * (1 - D.uncertainty)).toFixed(1);
      var hi = (km * (1 + D.uncertainty)).toFixed(1);
      var floor = s.nmin * D.street * D.detour / 1000;
      var fill = Math.min(100, s.nmin / Math.max(cap, s.nmin) * 100);

      var detail = ok
        ? "畫成 <b>" + (width / 1000).toFixed(1) + " km</b> 寬，取 <b>" + n +
          "</b> 個輪廓點，實際路線大約 <b>" + lo + "–" + hi + " km</b>"
        : "細節太多，" + km.toFixed(1) + " km 走不出來 —— 它至少需要 <b>" +
          floor.toFixed(1) + " km</b>";

      html += '<div class="row" data-ok="' + (ok ? 1 : 0) + '">' +
        '<svg viewBox="0 0 100 100" aria-hidden="true"><path d="' + s.path + '"></path></svg>' +
        '<div><div class="name">' + s.label +
        '<span class="cost">需要 ' + s.nmin + ' 個輪廓點</span></div>' +
        '<div class="detail">' + detail + '</div>' +
        '<div class="meter"><i style="width:' + fill + '%"></i></div></div>' +
        '<span class="verdict">' + (ok ? "可以" : "距離不夠") + '</span></div>';
    });
    rows.innerHTML = html;
  }

  slider.addEventListener("input", render);
  render();

  document.getElementById("foot").innerHTML =
    "數字來自實測，不是估計。街道尺度 160 公尺量自 POC 7；繞路比 " + D.detour +
    " 量自 POC 9 的 12 次擬合（標準差 0.07，隨圖案與尺寸變動），所以這裡給的是<b>區間而不是單一數字</b>" +
    " —— 12 次擬合全部落在 ±15% 內。<b>「距離不夠」不是把圖案鎖起來</b>：" +
    "在門檻以下，系統畫得出東西，但那個東西的定義性特徵會消失，而指標偵測不到 —— " +
    "所以這個檢查必須發生在畫之前。";
})();
</script>
"""


def main() -> None:
    shapes = []
    for key in SHAPES:
        pts = resample_by_arclength(key, 400)
        shapes.append({
            "key": key, "label": LABELS.get(key, key),
            "nmin": n_min(key), "perimeter": perimeter(key),
            "path": to_svg_path(pts, size=100.0, margin=10.0),
        })
    data = {"shapes": shapes, "street": TAIPEI_STREET_SCALE_M, "detour": DETOUR_RATIO,
            "fraction": WINDOW_FRACTION, "uncertainty": DETOUR_UNCERTAINTY}
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    OUT_HTML.write_text(PAGE.replace("__DATA__", payload))
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size / 1024:.0f} KB)")
    for s in sorted(shapes, key=lambda x: x["nmin"]):
        floor = s["nmin"] * TAIPEI_STREET_SCALE_M * DETOUR_RATIO / 1000
        print(f"  {s['label']:<6} n_min {s['nmin']:>3}  floor {floor:>5.1f} km")


if __name__ == "__main__":
    main()
