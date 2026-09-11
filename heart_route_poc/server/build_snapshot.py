"""
Freeze a few routes into one page anyone can open without running the service.

The service is the real thing, but it only exists while someone is running it.
This asks it for a handful of routes and writes them into a standalone file -
same drawing code, same street basemap, same rotation toggle, no server.

GPX download is deliberately absent: a published artifact runs in a sandbox
where a download link never fires, and a button that silently does nothing is
worse than no button.

Run:  python server/app.py --port 8016      (in another terminal)
      python server/build_snapshot.py
Out:  server/snapshot.html
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8016"
OUT = HERE / "snapshot.html"

WANTED = [
    ("heart", 10.0, "bike"),
    ("crescent", 9.0, "bike"),
    ("triangle", 8.0, "bike"),
    ("star5", 14.0, "bike"),
]


def ask(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def main() -> None:
    routes = []
    for shape, km, mode in WANTED:
        print(f"  {shape} at {km} km...", flush=True)
        r = ask("/api/route", {"shape": shape, "target_km": km, "mode": mode})
        if r.get("status") != "ok":
            print(f"    skipped: {r.get('status') or r.get('error')}")
            continue
        r.pop("gpx_url", None)
        r.pop("id", None)
        routes.append(r)
        print(f"    {r['route_km']} km, {len(r['streets'])} street lines")

    template = TEMPLATE.replace("__ROUTES__", json.dumps(routes, ensure_ascii=False,
                                                        separators=(",", ":")))
    OUT.write_text(template, encoding="utf-8")
    print(f"\nwrote {OUT.name}: {len(routes)} routes, "
          f"{OUT.stat().st_size / 1024 / 1024:.1f} MB")


TEMPLATE = r"""<title>台北的圖案路線</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root {
    --ground: #f6f5f1; --panel: #fffefb; --ink: #191b1a; --muted: #6d716d;
    --rule: #ddddd6; --accent: #2f5d50; --accent-soft: #e4ece8; --focus: #b4622c;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #16181a; --panel: #1f2224; --ink: #e9e9e3; --muted: #9aa09c;
      --rule: #333739; --accent: #7fbfa9; --accent-soft: #23302c; --focus: #e08a4d;
    }
  }
  :root[data-theme="dark"] {
    --ground: #16181a; --panel: #1f2224; --ink: #e9e9e3; --muted: #9aa09c;
    --rule: #333739; --accent: #7fbfa9; --accent-soft: #23302c; --focus: #e08a4d;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--ground); color: var(--ink);
    font-family: "IBM Plex Sans", system-ui, sans-serif; line-height: 1.6;
    padding-inline: 20px; padding-block: 32px 60px;
  }
  .wrap { max-width: 900px; margin: 0 auto; }
  .eyebrow {
    font-family: "IBM Plex Mono", monospace; font-size: 12px; letter-spacing: .09em;
    text-transform: uppercase; color: var(--muted); margin: 0 0 6px;
  }
  h1 { font-size: 30px; font-weight: 600; margin: 0 0 12px; text-wrap: balance; }
  .lede { color: var(--muted); max-width: 62ch; margin: 0 0 24px; }
  .picker { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
  .picker button {
    font: inherit; padding: 9px 18px; border-radius: 999px; cursor: pointer;
    background: var(--panel); color: var(--ink); border: 1px solid var(--rule);
  }
  .picker button[aria-pressed="true"] {
    border-color: var(--accent); color: var(--accent); font-weight: 500;
    background: var(--accent-soft);
  }
  .views { display: flex; gap: 6px; margin-bottom: 10px; }
  .views button {
    font: inherit; font-size: 13px; padding: 5px 14px; cursor: pointer;
    background: var(--panel); color: var(--ink);
    border: 1px solid var(--rule); border-radius: 999px;
  }
  .views button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); font-weight: 500; }
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) 230px; gap: 22px; }
  @media (max-width: 700px) { .layout { grid-template-columns: 1fr; } }
  .preview { background: #fff; border: 1px solid var(--rule); border-radius: 4px; }
  .preview svg { display: block; width: 100%; height: auto; }
  dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; font-size: 14px; }
  dt { color: var(--muted); }
  dd { margin: 0; font-family: "IBM Plex Mono", monospace; font-variant-numeric: tabular-nums; }
  .card {
    background: var(--panel); border: 1px solid var(--rule);
    border-radius: 4px; padding: 20px; margin-bottom: 18px;
  }
  .note { font-size: 13px; color: var(--muted); border-top: 1px solid var(--rule); padding-top: 14px; margin-top: 18px; }
  button:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
</style>

<div class="wrap">
  <p class="eyebrow">凍結的快照</p>
  <h1>台北的圖案路線</h1>
  <p class="lede">這幾條路線是在台北的單車路網上算出來的，沿著真實可以騎的道路。
    底圖不是圖磚，是這些路線實際被比對的那份路網本身。</p>

  <div class="card">
    <div class="picker" id="picker" role="group" aria-label="選路線"></div>
    <div class="layout">
      <div>
        <div class="views" role="group" aria-label="顯示方式">
          <button id="v-map" type="button" aria-pressed="true">路網底圖</button>
          <button id="v-shape" type="button" aria-pressed="false">只看形狀</button>
          <button id="v-north" type="button" aria-pressed="false">正北朝上</button>
        </div>
        <div class="preview" id="preview"></div>
      </div>
      <div>
        <dl id="stats"></dl>
        <p class="note">這是快照，沒有下載按鈕 —— 這個頁面跑在沙箱裡，下載連結不會有反應。
          GPX 檔要從對話裡拿，或自己跑 <code>python server/app.py</code>。</p>
      </div>
    </div>
  </div>
</div>

<script>
(function () {
  var ROUTES = __ROUTES__;
  var state = { index: 0, view: "map", upright: true };
  function $(id) { return document.getElementById(id); }

  function draw() {
    var r = ROUTES[state.index];
    var coords = r.coordinates;
    var streets = state.view === "map" ? (r.streets || []) : [];
    var all = streets.length ? [].concat.apply(coords.slice(), streets) : coords;
    var lats = all.map(function (c) { return c[0]; });
    var lons = all.map(function (c) { return c[1]; });
    var minLat = Math.min.apply(null, lats), maxLat = Math.max.apply(null, lats);
    var minLon = Math.min.apply(null, lons);
    var k = Math.cos((minLat + maxLat) / 2 * Math.PI / 180);

    var theta = (state.upright ? -(r.rotation_deg || 0) : 0) * Math.PI / 180;
    var cos = Math.cos(theta), sin = Math.sin(theta);
    function project(c) {
      var x = (c[1] - minLon) * k, y = maxLat - c[0];
      return [x * cos - y * sin, x * sin + y * cos];
    }
    var xs = [], ys = [];
    all.forEach(function (c) { var q = project(c); xs.push(q[0]); ys.push(q[1]); });
    var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
    var minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
    var w = maxX - minX, h = maxY - minY;
    var pad = Math.max(w, h) * 0.03, unit = Math.max(w, h);

    function pathOf(pts) {
      return pts.map(function (c, i) {
        var q = project(c);
        return (i ? "L" : "M") + (q[0] - minX).toFixed(6) + " " + (q[1] - minY).toFixed(6);
      }).join(" ");
    }

    var svg = '<svg viewBox="' + (-pad) + ' ' + (-pad) + ' ' + (w + 2 * pad) + ' '
      + (h + 2 * pad) + '" xmlns="http://www.w3.org/2000/svg">'
      + '<rect x="' + (-pad) + '" y="' + (-pad) + '" width="' + (w + 2 * pad)
      + '" height="' + (h + 2 * pad) + '" fill="#f4f2ec"/>';
    if (streets.length) {
      svg += '<g stroke="#c9c6bd" stroke-width="' + (unit / 900) + '" fill="none" stroke-linecap="round">';
      streets.forEach(function (s) { svg += '<path d="' + pathOf(s) + '"/>'; });
      svg += "</g>";
    }
    svg += '<path d="' + pathOf(coords) + '" fill="none" stroke="#c0392b" stroke-width="'
      + (unit / 260) + '" stroke-linejoin="round" stroke-linecap="round"/>';
    var arrow = unit * 0.07, ax = w - arrow * 0.7, ay = arrow * 1.1;
    svg += '<g transform="translate(' + ax + ' ' + ay + ') rotate(' + (theta * 180 / Math.PI)
      + ')" stroke="#6d716d" fill="#6d716d" stroke-width="' + (unit / 700) + '">'
      + '<line x1="0" y1="' + (arrow / 2) + '" x2="0" y2="' + (-arrow / 2) + '"/>'
      + '<path d="M' + (-arrow / 5) + ' ' + (-arrow / 4) + ' L0 ' + (-arrow / 2) + ' L'
      + (arrow / 5) + ' ' + (-arrow / 4) + ' Z" stroke="none"/></g>'
      + '<text x="' + ax + '" y="' + (ay + arrow * 0.95) + '" font-size="' + (unit / 22)
      + '" fill="#6d716d" text-anchor="middle" font-family="system-ui, sans-serif">N</text></svg>';
    $("preview").innerHTML = svg;

    $("stats").innerHTML =
      "<dt>圖案</dt><dd>" + r.label + "</dd>"
      + "<dt>距離</dt><dd>" + r.route_km + " km</dd>"
      + "<dt>畫多寬</dt><dd>" + (r.width_m / 1000).toFixed(1) + " km</dd>"
      + "<dt>輪廓點</dt><dd>" + r.points + "</dd>"
      + "<dt>擺放角度</dt><dd>" + r.rotation_deg + "°</dd>"
      + "<dt>形狀誤差</dt><dd>" + r.shape_distance + "</dd>";
  }

  ROUTES.forEach(function (r, i) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = r.label + " · " + r.route_km + " km";
    b.setAttribute("aria-pressed", String(i === 0));
    b.addEventListener("click", function () {
      state.index = i;
      Array.prototype.forEach.call($("picker").children, function (c, j) {
        c.setAttribute("aria-pressed", String(j === i));
      });
      draw();
    });
    $("picker").appendChild(b);
  });

  function setView(which) {
    state.view = which;
    $("v-map").setAttribute("aria-pressed", String(which === "map"));
    $("v-shape").setAttribute("aria-pressed", String(which !== "map"));
    draw();
  }
  $("v-map").addEventListener("click", function () { setView("map"); });
  $("v-shape").addEventListener("click", function () { setView("shape"); });
  $("v-north").addEventListener("click", function () {
    state.upright = !state.upright;
    $("v-north").setAttribute("aria-pressed", String(!state.upright));
    $("v-north").textContent = state.upright ? "正北朝上" : "轉正圖案";
    draw();
  });

  draw();
})();
</script>
"""


if __name__ == "__main__":
    main()
