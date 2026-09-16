"""
Build the blind identification task page from POC 32's stimuli.

Two per shape - the closest fit and the worst - so one task answers both
questions at once: whether the drawing reads at all (the closest fit), and
where it stops reading (the pair, across fifteen shapes, gives the slope).

Deliberately withheld from the rater: the distance, the kilometres, the city,
and any reference outline. POC 28 established why - once you have been told it
is a heart you cannot un-know it, and the question collapses back into
discrimination. Even the length is a cue, since a longer ride means a bigger
shape.

Answers go to the artifact's own store rather than to a clipboard, with the
copy-paste path kept for a viewer whose browser refuses.

Run:  python -m experiments.poc32_build_task
Out:  results/poc32_task.html
"""

from __future__ import annotations

import json

import routeshape.shapes.pack as pack
from routeshape.paths import RESULTS

STIMULI = RESULTS / "poc32_stimuli.json"
OUT = RESULTS / "poc32_task.html"
PER_SHAPE = 2


def pick(rows: list) -> list:
    """The closest fit and the worst, per shape."""
    by_shape: dict = {}
    for row in rows:
        by_shape.setdefault(row["shape"], []).append(row)
    out = []
    for shape, group in by_shape.items():
        group.sort(key=lambda r: r["distance"])
        chosen = [group[0]] if len(group) == 1 else [group[0], group[-1]]
        out.extend(chosen[:PER_SHAPE])
    return out


def main() -> None:
    rows = json.loads(STIMULI.read_text())
    items = pick(rows)
    labels = dict(pack.LABELS)
    options = [{"name": n, "label": labels.get(n, n)} for n in sorted(labels)]
    payload = {
        "options": options,
        "items": [{"id": f"{r['shape']}_{i}", "shape": r["shape"],
                   "distance": r["distance"], "route_km": r["route_km"],
                   "xy": r["xy"]}
                  for i, r in enumerate(items)],
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    OUT.write_text(html, encoding="utf-8")
    print(f"{len(items)} items over {len(set(i['shape'] for i in items))} shapes")
    print(f"distances {min(i['distance'] for i in items):.3f}"
          f"-{max(i['distance'] for i in items):.3f}")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1000:.0f} KB)")


TEMPLATE = r"""<title>這條路線在畫什麼</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root {
    --ground: #f6f5f1; --panel: #fffefb; --ink: #191b1a; --muted: #6d716d;
    --rule: #ddddd6; --accent: #2f5d50; --accent-soft: #e4ece8;
    --focus: #b4622c; --route: #b23b2c; --paper: #f0eee7;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #16181a; --panel: #1f2224; --ink: #e9e9e3; --muted: #9aa09c;
      --rule: #333739; --accent: #7fbfa9; --accent-soft: #23302c;
      --focus: #e08a4d; --route: #e2735e; --paper: #191c1e;
    }
  }
  :root[data-theme="dark"] {
    --ground: #16181a; --panel: #1f2224; --ink: #e9e9e3; --muted: #9aa09c;
    --rule: #333739; --accent: #7fbfa9; --accent-soft: #23302c;
    --focus: #e08a4d; --route: #e2735e; --paper: #191c1e;
  }

  body {
    background: var(--ground); color: var(--ink);
    font-family: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
    line-height: 1.6; margin: 0;
    padding-inline: 20px; padding-block: 28px 56px;
  }
  .wrap { max-width: 720px; margin: 0 auto; }
  .mono {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-variant-numeric: tabular-nums;
  }
  .eyebrow {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 12px; letter-spacing: 0.09em; text-transform: uppercase;
    color: var(--muted); margin: 0 0 8px;
  }
  h1 { font-size: 26px; font-weight: 600; margin: 0 0 14px; text-wrap: balance; }
  p { margin: 0 0 14px; }
  .lede { color: var(--muted); max-width: 60ch; }
  ul { color: var(--muted); max-width: 60ch; padding-left: 20px; margin: 0 0 18px; }
  li { margin-bottom: 6px; }

  .progress { display: flex; gap: 3px; margin: 0 0 14px; }
  .progress span { flex: 1; height: 3px; background: var(--rule); border-radius: 2px; }
  .progress span.done { background: var(--accent); }
  .progress span.now { background: var(--focus); }

  .counter {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums;
    display: flex; justify-content: space-between; margin-bottom: 10px;
  }

  .stage {
    background: var(--paper); border: 1px solid var(--rule); border-radius: 3px;
    padding: 10px; margin-bottom: 18px;
  }
  .stage svg { display: block; width: 100%; height: auto; max-width: 100%; }

  .prompt { font-size: 17px; font-weight: 500; margin: 0 0 12px; }

  .options { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  @media (max-width: 560px) { .options { grid-template-columns: repeat(3, 1fr); } }
  .options button, .wide {
    font: inherit; font-size: 15px; padding: 10px 6px; cursor: pointer;
    background: var(--panel); color: var(--ink);
    border: 1px solid var(--rule); border-radius: 3px;
  }
  .options button:hover { border-color: var(--accent); color: var(--accent); }
  .options button:focus-visible, .wide:focus-visible {
    outline: 2px solid var(--focus); outline-offset: 2px;
  }
  .wide {
    grid-column: 1 / -1; margin-top: 4px; color: var(--muted);
  }
  .wide:hover { border-color: var(--focus); color: var(--focus); }

  .start {
    font: inherit; font-size: 16px; font-weight: 500; padding: 11px 22px;
    cursor: pointer; background: var(--accent); color: var(--ground);
    border: 1px solid var(--accent); border-radius: 3px;
  }
  .start:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

  .status { color: var(--muted); font-size: 14px; margin-top: 14px; }
  textarea {
    width: 100%; box-sizing: border-box; min-height: 130px; margin-top: 10px;
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11px;
    background: var(--panel); color: var(--ink);
    border: 1px solid var(--rule); border-radius: 3px; padding: 8px;
  }
  .tally { border-top: 1px solid var(--rule); margin-top: 22px; padding-top: 16px; }
  .tally dl {
    display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; margin: 0;
    font-size: 14px;
  }
  .tally dt { color: var(--muted); }
  .tally dd { margin: 0; }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap"><div id="app"></div></div>

<script>
var DATA = __DATA__;

var app = document.getElementById("app");
var answers = [];
var order = [];
var at = 0;
var sessionId = (Date.now().toString(36) + Math.random().toString(36).slice(2, 8));

function el(tag, attrs, kids) {
  var n = document.createElement(tag);
  for (var k in (attrs || {})) {
    if (k === "class") n.className = attrs[k];
    else if (k === "text") n.textContent = attrs[k];
    else n.setAttribute(k, attrs[k]);
  }
  (kids || []).forEach(function (c) { n.appendChild(c); });
  return n;
}

// Shuffle, then push apart any two neighbours of the same shape. Seeing the
// same shape twice in a row tells the rater the second one is the same shape,
// which is information the task is supposed to withhold.
function arrange(items) {
  var idx = items.map(function (_, i) { return i; });
  for (var i = idx.length - 1; i > 0; i--) {
    var j = Math.floor(Math.random() * (i + 1));
    var t = idx[i]; idx[i] = idx[j]; idx[j] = t;
  }
  for (var p = 1; p < idx.length; p++) {
    if (items[idx[p]].shape !== items[idx[p - 1]].shape) continue;
    for (var q = p + 1; q < idx.length; q++) {
      if (items[idx[q]].shape === items[idx[p - 1]].shape) continue;
      var s = idx[p]; idx[p] = idx[q]; idx[q] = s;
      break;
    }
  }
  return idx;
}

function routeSvg(xy) {
  var d = "";
  for (var i = 0; i < xy.length; i++) {
    d += (i ? "L" : "M") + xy[i][0].toFixed(4) + " " + (-xy[i][1]).toFixed(4);
  }
  d += "Z";
  var ns = "http://www.w3.org/2000/svg";
  var svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "-1.15 -1.15 2.3 2.3");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "一條單車路線");
  var path = document.createElementNS(ns, "path");
  path.setAttribute("d", d);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", getComputedStyle(document.body).getPropertyValue("--route").trim() || "#b23b2c");
  path.setAttribute("stroke-width", "0.022");
  path.setAttribute("stroke-linejoin", "round");
  path.setAttribute("stroke-linecap", "round");
  svg.appendChild(path);
  return svg;
}

function intro() {
  app.innerHTML = "";
  app.appendChild(el("p", {class: "eyebrow", text: "辨識測驗 · 15 個圖案 · 約 4 分鐘"}));
  app.appendChild(el("h1", {text: "這條路線在畫什麼？"}));
  app.appendChild(el("p", {class: "lede", text:
    "下面每一張都是一條真的單車路線，沿著台北的街道跑出來的，目標是在地圖上畫出某個形狀。你的工作是看著紅線，說出它想畫的是什麼。"}));
  var ul = el("ul");
  [
    "一次只看一張，沒有參考圖，也不會告訴你答案。",
    "從選項裡選一個。真的看不出來就按「看不出來」——這不是認輸，它跟其他答案一樣重要。",
    "憑第一眼，不要盯著想。想久了你會開始說服自己。",
    "同一個形狀會出現兩次，難度不同。"
  ].forEach(function (t) { ul.appendChild(el("li", {text: t})); });
  app.appendChild(ul);
  var b = el("button", {class: "start", text: "開始"});
  b.onclick = function () { order = arrange(DATA.items); at = 0; step(); };
  app.appendChild(b);
}

function step() {
  if (at >= order.length) { return done(); }
  var item = DATA.items[order[at]];
  app.innerHTML = "";

  var bar = el("div", {class: "progress"});
  for (var i = 0; i < order.length; i++) {
    bar.appendChild(el("span", {class: i < at ? "done" : (i === at ? "now" : "")}));
  }
  app.appendChild(bar);
  app.appendChild(el("div", {class: "counter"}, [
    el("span", {text: "第 " + (at + 1) + " / " + order.length + " 題"}),
    el("span", {text: "看不出來也是答案"})
  ]));

  var stage = el("div", {class: "stage"});
  stage.appendChild(routeSvg(item.xy));
  app.appendChild(stage);

  app.appendChild(el("p", {class: "prompt", text: "這在畫什麼？"}));

  var grid = el("div", {class: "options"});
  DATA.options.forEach(function (o) {
    var b = el("button", {text: o.label, type: "button"});
    b.onclick = function () { answer(item, o.name); };
    grid.appendChild(b);
  });
  var none = el("button", {class: "wide", text: "看不出來", type: "button"});
  none.onclick = function () { answer(item, "__none__"); };
  grid.appendChild(none);
  app.appendChild(grid);
  window.scrollTo(0, 0);
}

function answer(item, chosen) {
  answers.push({
    item: item.id, shape: item.shape, distance: item.distance,
    route_km: item.route_km, chosen: chosen,
    correct: chosen === item.shape, at: Date.now()
  });
  at += 1;
  step();
}

function done() {
  app.innerHTML = "";
  app.appendChild(el("p", {class: "eyebrow", text: "完成"}));
  app.appendChild(el("h1", {text: "做完了，謝謝"}));
  app.appendChild(el("p", {class: "lede", text:
    "這些答案會決定哪些圖案要重畫、哪些要砍掉，以及每個圖案要騎多遠才畫得出來。"}));

  var right = answers.filter(function (a) { return a.correct; }).length;
  var blank = answers.filter(function (a) { return a.chosen === "__none__"; }).length;
  var tally = el("div", {class: "tally"});
  var dl = el("dl");
  [["認對", right + " / " + answers.length],
   ["看不出來", String(blank)],
   ["認錯", String(answers.length - right - blank)]].forEach(function (pair) {
    dl.appendChild(el("dt", {text: pair[0]}));
    dl.appendChild(el("dd", {class: "mono", text: pair[1]}));
  });
  tally.appendChild(dl);
  app.appendChild(tally);

  var status = el("p", {class: "status", text: "正在儲存…"});
  app.appendChild(status);
  var payload = {session: sessionId, finished: new Date().toISOString(),
                 answers: answers};

  function fallback(msg) {
    status.textContent = msg + "請把下面這段文字整個複製傳回去。";
    var ta = el("textarea", {readonly: "readonly", id: "payload"});
    ta.value = JSON.stringify(payload);
    app.appendChild(ta);
    ta.focus(); ta.select();
  }

  if (!window.claude || !window.claude.use) {
    return fallback("這個頁面沒有連上儲存空間。");
  }
  window.claude.use("db").then(function (db) {
    if (!db) { return fallback("這個裝置無法自動儲存。"); }
    return db.doc("responses/" + sessionId).set(payload).then(function () {
      status.textContent = "已儲存（" + sessionId + "）。可以關掉這一頁了。";
    });
  }).catch(function () {
    fallback("自動儲存失敗。");
  });
}

intro();
</script>
"""


if __name__ == "__main__":
    main()
