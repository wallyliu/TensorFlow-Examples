"""
Build the anchored blind identification task.

Twenty-one shapes - the sixteen in the pack plus the five POC 29 measured -
two items each, one option list, one set of raters. The anchors are the point:
whatever this task's option count and this task's people do to the numbers,
they do it to the old shapes too, so the pack can finally be compared against
them without the confounds POC 32 had to print beside its p-value.

The rater is not told which are which, and the anchors are spread through the
running order like everything else.

Run:  python -m experiments.poc33_build_task
Out:  results/poc33_task.html
"""

from __future__ import annotations

import json

import routeshape.shapes.pack as pack
from experiments.poc32_build_task import TEMPLATE, pick
from routeshape.paths import RESULTS

STIMULI = RESULTS / "poc33_stimuli.json"
OUT = RESULTS / "poc33_task.html"
ANCHOR_LABELS = {"triangle": "三角形", "heart": "愛心", "star5": "五角星",
                 "crescent": "月亮", "trex": "恐龍"}


def main() -> None:
    rows = json.loads(STIMULI.read_text())
    items = pick(rows)
    labels = dict(pack.LABELS) | ANCHOR_LABELS
    payload = {
        "options": [{"name": n, "label": labels[n]} for n in sorted(labels)],
        "items": [{"id": f"{r['shape']}_{i}", "shape": r["shape"],
                   "anchor": bool(r.get("anchor")),
                   "distance": r["distance"], "route_km": r["route_km"],
                   "xy": r["xy"]}
                  for i, r in enumerate(items)],
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    html = html.replace("15 個圖案 · 約 4 分鐘", "21 個圖案 · 約 7 分鐘")
    # A distinct name, so the two rounds do not sit in the gallery under one
    # title and get opened by the wrong people.
    html = html.replace("<title>這條路線在畫什麼</title>",
                        "<title>路線辨識第二輪</title>")
    OUT.write_text(html, encoding="utf-8")
    anchors = sum(i["anchor"] for i in payload["items"])
    print(f"{len(items)} items over {len(labels)} shapes "
          f"({anchors} anchor items), {len(payload['options'])} options")
    print(f"distances {min(i['distance'] for i in payload['items']):.3f}"
          f"-{max(i['distance'] for i in payload['items']):.3f}")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1000:.0f} KB)")


if __name__ == "__main__":
    main()
