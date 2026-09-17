"""
Build the hand-drawn-against-traced task.

The rater picks a SUBJECT, so a shape that exists in both arms has the same
right answer either way and the option list gives nothing away. The two arms
are never adjacent in the running order - seeing the same subject twice in a
row tells you the second one is the same subject, which is the one thing this
task must not leak.

Run:  python -m experiments.poc36_build_task
Out:  results/poc36_task.html
"""

from __future__ import annotations

import json

from experiments.poc32_build_task import TEMPLATE
from routeshape.paths import RESULTS

STIMULI = RESULTS / "poc36_stimuli.json"
OUT = RESULTS / "poc36_task.html"


def main() -> None:
    rows = json.loads(STIMULI.read_text())
    labels = {}
    for row in rows:
        labels.setdefault(row["label"], row["label"])
    payload = {
        "options": [{"name": label, "label": label} for label in sorted(labels)],
        # `shape` is the LABEL, so `correct` in the answers means "named the
        # subject", which is what both arms are being scored on. The arm and
        # the drawing it came from ride along for the analysis.
        "items": [{"id": f"{r['shape']}_{i}", "shape": r["label"],
                   "drawing": r["shape"], "arm": r["arm"],
                   "distance": r["distance"], "excursion": r["excursion"],
                   "route_km": r["route_km"], "xy": r["xy"]}
                  for i, r in enumerate(rows)],
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    html = html.replace("15 個圖案 · 約 4 分鐘",
                        f"{len(payload['options'])} 個選項 · 約 5 分鐘")
    html = html.replace("<title>這條路線在畫什麼</title>",
                        "<title>路線辨識第三輪</title>")
    html = html.replace("同一個形狀會出現兩次，難度不同。",
                        "有些東西會出現兩次，是用不同的畫法畫的。")
    OUT.write_text(html, encoding="utf-8")
    arms = {}
    for item in payload["items"]:
        arms[item["arm"]] = arms.get(item["arm"], 0) + 1
    print(f"{len(payload['items'])} items, {len(payload['options'])} options, "
          f"arms {arms}")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1000:.0f} KB)")


if __name__ == "__main__":
    main()
