"""
Build round five's task page.

One arm, one item per shape, so this is the plain version of the instrument:
look at a route, name the subject. No pairs to keep apart and no tracer to
split - POC 37 settled that question and this round is only filling in the
shapes nobody has seen.

Run:  python -m experiments.poc41_build_task
Out:  results/poc41_task.html
"""

from __future__ import annotations

import json

from experiments.poc32_build_task import TEMPLATE
from routeshape.paths import RESULTS

STIMULI = RESULTS / "poc41_stimuli.json"
OUT = RESULTS / "poc41_task.html"


def main() -> None:
    rows = json.loads(STIMULI.read_text())
    labels = sorted({row["label"] for row in rows})
    payload = {
        "options": [{"name": label, "label": label} for label in labels],
        "items": [{"id": f"{r['shape']}_{i}", "shape": r["label"],
                   "subject": r["subject"], "drawing": r["shape"],
                   "arm": r["arm"], "distance": r["distance"],
                   "excursion": r["excursion"], "route_km": r["route_km"],
                   "xy": r["xy"]}
                  for i, r in enumerate(rows)],
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    html = html.replace("15 個圖案 · 約 4 分鐘",
                        f"{len(labels)} 個選項 · 約 5 分鐘")
    html = html.replace("<title>這條路線在畫什麼</title>",
                        "<title>路線辨識第五輪</title>")
    # No shape appears twice in this round, so the sentence warning about it
    # would be a lie - and a rater who expects repeats will look for them.
    html = html.replace("<li>同一個形狀會出現兩次，難度不同。</li>", "")
    html = html.replace("同一個形狀會出現兩次，難度不同。", "")
    OUT.write_text(html, encoding="utf-8")
    print(f"{len(payload['items'])} items, {len(labels)} options")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1000:.0f} KB)")


if __name__ == "__main__":
    main()
