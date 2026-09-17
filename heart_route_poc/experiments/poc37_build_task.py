"""
Build round four's task page.

Each subject was fitted three times - hand-drawn, Noto-traced, OpenMoji-traced
- but a rater sees it TWICE: the hand arm, and one of the two emoji arms drawn
at random when the page loads. Three sightings of one subject would make the
third a memory test rather than a recognition test, and the choice of tracer is
a second question that a rater cannot answer by seeing both.

The rater picks a SUBJECT, so every arm of a subject has the same right answer
and the option list gives nothing away.

Run:  python -m experiments.poc37_build_task
Out:  results/poc37_task.html
"""

from __future__ import annotations

import json

from experiments.poc32_build_task import TEMPLATE
from routeshape.paths import RESULTS

STIMULI = RESULTS / "poc37_stimuli.json"
OUT = RESULTS / "poc37_task.html"

# Drop one of the two emoji arms per subject, per rater, at load time. Anything
# that is not part of a pair (the anchors) is kept as it is.
PICK = """
(function () {
  var by = {};
  DATA.items.forEach(function (it) {
    (by[it.subject] = by[it.subject] || []).push(it);
  });
  var keep = [];
  Object.keys(by).forEach(function (k) {
    var pool = by[k].filter(function (i) { return i.arm !== 'hand'
                                                  && i.arm !== 'anchor'; });
    var pick = pool.length ? pool[Math.floor(Math.random() * pool.length)] : null;
    by[k].forEach(function (i) {
      if (i.arm === 'hand' || i.arm === 'anchor' || i === pick) keep.push(i);
    });
  });
  DATA.items = keep;
})();
"""


def main() -> None:
    rows = json.loads(STIMULI.read_text())
    labels = sorted({row["label"] for row in rows})
    payload = {
        "options": [{"name": label, "label": label} for label in labels],
        # `shape` is the LABEL, so `correct` in the answers means "named the
        # subject" - what every arm is scored on - and `arrange` keeps two
        # drawings of one subject off each other's heels.
        "items": [{"id": f"{r['shape']}_{i}", "shape": r["label"],
                   "subject": r["subject"], "drawing": r["shape"],
                   "arm": r["arm"], "distance": r["distance"],
                   "excursion": r["excursion"], "route_km": r["route_km"],
                   "xy": r["xy"]}
                  for i, r in enumerate(rows)],
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    anchor = "function arrange(items) {"
    if anchor not in html:
        raise RuntimeError("the task template changed; PICK has nowhere to go")
    html = html.replace(anchor, PICK + "\n" + anchor, 1)
    html = html.replace("15 個圖案 · 約 4 分鐘",
                        f"{len(labels)} 個選項 · 約 5 分鐘")
    html = html.replace("<title>這條路線在畫什麼</title>",
                        "<title>路線辨識第四輪</title>")
    html = html.replace("同一個形狀會出現兩次，難度不同。",
                        "有些東西會出現兩次，是用不同的畫法畫的。")
    OUT.write_text(html, encoding="utf-8")
    arms: dict = {}
    for item in payload["items"]:
        arms[item["arm"]] = arms.get(item["arm"], 0) + 1
    print(f"{len(payload['items'])} items pooled, {len(labels)} options, "
          f"arms {arms}")
    print(f"each rater sees {sum(1 for i in payload['items'] if i['arm'] in ('hand', 'anchor'))}"
          f" + one emoji arm per paired subject")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1000:.0f} KB)")


if __name__ == "__main__":
    main()
