"""
Build the rater task page for POC 13.

Two questions in one sitting, both of which the project cannot answer for itself:

1. Does equal shape distance mean equal damage? An iso-distance ladder pits a
   destroyed feature against noise of identical metric distance, four times over.
   If the metric says what a person sees, the rater has no preference at any rung.

2. Is the metric inverted for text? POC 12 found tilted, unreadable "LIT" routes
   scoring BETTER than upright readable ones. Here a rater who is never shown a
   score decides which they can read.

Three instrument rules, each bought with a previous round's mistake:

  - Click only. POC 5 bound "tie" to the spacebar with 0 ms of travel against
    160 ms for a mouse choice, and collected 17 ties in 47 seconds.
  - Four options, and neither member of a pair is the clean shape. POC 6's v2
    anchored every pair to a clean route, which guaranteed one good member and
    recorded zero "neither" answers.
  - The first two trials run before the word "LIT" appears anywhere on the page.
    After that the rater is primed and cannot be unprimed.

Run:  python poc13_build_task.py
Out:  poc13_task.html
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

RATER = Path(__file__).with_name("rater")
OUT = Path(__file__).with_name("poc13_task.html")

IMAGES = [
    "dino_clean", "dino_scrambled",
    "dino_L1_merged", "dino_L1_noise", "dino_L2_merged", "dino_L2_noise",
    "dino_L3_merged", "dino_L3_noise", "dino_L4_merged", "dino_L4_noise",
    "lit_outline_free", "lit_outline_upright",
    "lit_stroke_free", "lit_stroke_upright",
]

PAIR_OPTIONS = ["左邊比較像", "右邊比較像", "兩個差不多", "兩個都不像"]
RATE_OPTIONS = ["很像", "有點像", "不太像", "完全看不出是字"]
READ_OPTIONS = ["LIT", "HIT", "UT", "看不出來"]

TRIALS = [
    # Section 0 - before the answer appears anywhere on the page.
    {"id": "read_outline", "section": "read", "kind": "single",
     "image": "lit_outline_upright", "options": READ_OPTIONS,
     "prompt": "這條路線是照一個英文單字畫出來的。你覺得是哪一個？"},
    {"id": "read_stroke", "section": "read", "kind": "single",
     "image": "lit_stroke_upright", "options": READ_OPTIONS,
     "prompt": "這條路線是照一個英文單字畫出來的。你覺得是哪一個？"},

    # Section 1 - the iso-distance ladder. Both members of every pair are
    # damaged, and by the same amount as far as the metric is concerned.
    {"id": "catch_clean", "section": "dino", "kind": "pair", "catch": True,
     "a": "dino_clean", "b": "dino_scrambled", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像恐龍？"},
    {"id": "L1", "section": "dino", "kind": "pair",
     "a": "dino_L1_merged", "b": "dino_L1_noise", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像恐龍？"},
    {"id": "L2", "section": "dino", "kind": "pair",
     "a": "dino_L2_merged", "b": "dino_L2_noise", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像恐龍？"},
    {"id": "L3", "section": "dino", "kind": "pair",
     "a": "dino_L3_merged", "b": "dino_L3_noise", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像恐龍？"},
    {"id": "L4", "section": "dino", "kind": "pair",
     "a": "dino_L4_merged", "b": "dino_L4_noise", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像恐龍？"},
    {"id": "catch_bothbad", "section": "dino", "kind": "pair", "catch": True,
     "a": "dino_scrambled", "b": "dino_L4_noise", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像恐龍？"},
    {"id": "L2_repeat", "section": "dino", "kind": "pair", "repeat_of": "L2",
     "a": "dino_L2_merged", "b": "dino_L2_noise", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像恐龍？"},
    {"id": "L4_repeat", "section": "dino", "kind": "pair", "repeat_of": "L4",
     "a": "dino_L4_merged", "b": "dino_L4_noise", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像恐龍？"},

    # Section 2 - now the rater knows the word.
    {"id": "rate_outline_free", "section": "text", "kind": "single",
     "image": "lit_outline_free", "options": RATE_OPTIONS,
     "prompt": "這條路線像不像英文字「LIT」？"},
    {"id": "rate_outline_upright", "section": "text", "kind": "single",
     "image": "lit_outline_upright", "options": RATE_OPTIONS,
     "prompt": "這條路線像不像英文字「LIT」？"},
    {"id": "rate_stroke_free", "section": "text", "kind": "single",
     "image": "lit_stroke_free", "options": RATE_OPTIONS,
     "prompt": "這條路線像不像英文字「LIT」？"},
    {"id": "rate_stroke_upright", "section": "text", "kind": "single",
     "image": "lit_stroke_upright", "options": RATE_OPTIONS,
     "prompt": "這條路線像不像英文字「LIT」？"},
    {"id": "pair_outline", "section": "text", "kind": "pair",
     "a": "lit_outline_free", "b": "lit_outline_upright", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像英文字「LIT」？"},
    {"id": "pair_stroke", "section": "text", "kind": "pair",
     "a": "lit_stroke_free", "b": "lit_stroke_upright", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像英文字「LIT」？"},
]


def data_uri(name: str) -> str:
    raw = (RATER / f"{name}.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def main() -> None:
    images = {name: data_uri(name) for name in IMAGES}
    payload = json.dumps({"trials": TRIALS, "images": images},
                         ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(TEMPLATE.replace("__PAYLOAD__", payload), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT.name}: {len(TRIALS)} trials, {len(images)} images, {kb:.0f} KB")


TEMPLATE = r"""<title>這些路線看起來像什麼</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root {
    --ground: #f6f5f1;
    --panel: #fffefb;
    --ink: #191b1a;
    --muted: #6d716d;
    --rule: #ddddd6;
    --accent: #2f5d50;
    --accent-soft: #e4ece8;
    --focus: #b4622c;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #16181a;
      --panel: #1f2224;
      --ink: #e9e9e3;
      --muted: #9aa09c;
      --rule: #333739;
      --accent: #7fbfa9;
      --accent-soft: #23302c;
      --focus: #e08a4d;
    }
  }
  :root[data-theme="dark"] {
    --ground: #16181a;
    --panel: #1f2224;
    --ink: #e9e9e3;
    --muted: #9aa09c;
    --rule: #333739;
    --accent: #7fbfa9;
    --accent-soft: #23302c;
    --focus: #e08a4d;
  }

  body {
    background: var(--ground);
    color: var(--ink);
    font-family: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
    line-height: 1.6;
    margin: 0;
    padding-inline: 20px;
    padding-block: 28px 60px;
  }
  .wrap { max-width: 860px; margin: 0 auto; }

  .eyebrow {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 12px; letter-spacing: 0.09em; text-transform: uppercase;
    color: var(--muted); margin: 0 0 6px;
  }
  h1 { font-size: 27px; font-weight: 600; margin: 0 0 14px; text-wrap: balance; }
  p { margin: 0 0 14px; }
  .lede { color: var(--muted); max-width: 62ch; }

  .progress { display: flex; gap: 3px; margin: 22px 0 20px; }
  .progress span {
    flex: 1; height: 3px; background: var(--rule); border-radius: 2px;
  }
  .progress span.done { background: var(--accent); }
  .progress span.now { background: var(--focus); }

  .counter {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums;
  }

  .prompt { font-size: 19px; font-weight: 500; margin: 4px 0 18px; text-wrap: balance; }

  .stims { display: flex; gap: 14px; }
  .stims.one { justify-content: center; }
  .stim {
    flex: 1; min-width: 0;
    /* The stimuli are black line art on white. The card stays white in both
       themes on purpose - a dark card behind them would change what is being
       judged from one viewer to the next. */
    background: #ffffff;
    border: 1px solid var(--rule);
    border-radius: 3px;
    padding: 6px;
  }
  .stims.one .stim { max-width: 420px; }
  .stim img { display: block; width: 100%; height: auto; }
  .stim .side {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
    color: #8a8f8a; text-align: center; padding-top: 2px;
  }

  .options { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 20px; }
  button.opt {
    font: inherit; font-size: 15px;
    background: var(--panel); color: var(--ink);
    border: 1px solid var(--rule); border-radius: 3px;
    padding: 14px 10px; cursor: pointer;
    transition: background 120ms ease, border-color 120ms ease;
  }
  button.opt:hover { background: var(--accent-soft); border-color: var(--accent); }
  button.opt:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

  .note {
    font-size: 14px; color: var(--muted); margin-top: 18px;
    border-top: 1px solid var(--rule); padding-top: 14px;
  }

  .start { margin-top: 8px; }
  button.primary {
    font: inherit; font-size: 16px; font-weight: 500;
    background: var(--accent); color: var(--ground);
    border: none; border-radius: 3px; padding: 13px 26px; cursor: pointer;
  }
  button.primary:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

  pre.result {
    background: var(--panel); border: 1px solid var(--rule); border-radius: 3px;
    padding: 14px; font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 12px; overflow-x: auto; max-height: 320px; white-space: pre-wrap;
    word-break: break-all;
  }
  .saved { color: var(--accent); font-weight: 500; }

  @media (max-width: 700px) {
    .stims { flex-direction: column; }
    .options { grid-template-columns: repeat(2, 1fr); }
  }
  @media (prefers-reduced-motion: reduce) {
    button.opt { transition: none; }
  }
</style>

<div class="wrap">
  <div id="app"></div>
</div>

<script>
(function () {
  var DATA = __PAYLOAD__;
  var app = document.getElementById("app");

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  // Sides are randomised per trial so a rater cannot settle into "the left one
  // is always the good one", and the assignment is recorded with the answer.
  var order = DATA.trials.map(function (t) {
    return { trial: t, flipped: t.kind === "pair" && Math.random() < 0.5 };
  });

  var answers = [];
  var index = -1;
  var shownAt = 0;
  var sessionId = "r" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

  function progress() {
    var bar = el("div", "progress");
    for (var i = 0; i < order.length; i++) {
      var seg = el("span");
      if (i < index) seg.className = "done";
      else if (i === index) seg.className = "now";
      bar.appendChild(seg);
    }
    return bar;
  }

  function intro() {
    app.innerHTML = "";
    app.appendChild(el("p", "eyebrow", "路線形狀辨識"));
    app.appendChild(el("h1", null, "這些路線看起來像什麼？"));
    var p1 = el("p", "lede", "每一張圖都是一條真實的道路路線，照著某個圖案畫出來的。總共 "
      + order.length + " 題，大約五分鐘。");
    app.appendChild(p1);
    app.appendChild(el("p", "lede",
      "沒有標準答案，請照你第一眼的感覺選，不要回頭想。四個選項都只是按一下滑鼠，不要因為哪個比較好按就選它。"));
    var wrap = el("div", "start");
    var go = el("button", "primary", "開始");
    go.addEventListener("click", next);
    wrap.appendChild(go);
    app.appendChild(wrap);
  }

  function stimCard(name, label) {
    var card = el("div", "stim");
    var img = document.createElement("img");
    img.src = DATA.images[name];
    img.alt = "路線圖";
    card.appendChild(img);
    if (label) card.appendChild(el("div", "side", label));
    return card;
  }

  function render() {
    var item = order[index];
    var t = item.trial;
    app.innerHTML = "";
    app.appendChild(progress());
    app.appendChild(el("div", "counter", "第 " + (index + 1) + " 題 / 共 " + order.length + " 題"));
    app.appendChild(el("div", "prompt", t.prompt));

    var stims = el("div", "stims" + (t.kind === "single" ? " one" : ""));
    if (t.kind === "single") {
      stims.appendChild(stimCard(t.image, null));
    } else {
      var left = item.flipped ? t.b : t.a;
      var right = item.flipped ? t.a : t.b;
      stims.appendChild(stimCard(left, "左"));
      stims.appendChild(stimCard(right, "右"));
    }
    app.appendChild(stims);

    var opts = el("div", "options");
    t.options.forEach(function (label, i) {
      var b = el("button", "opt", label);
      b.type = "button";
      b.id = "opt-" + t.id + "-" + i;
      b.addEventListener("click", function () { answer(i, label); });
      opts.appendChild(b);
    });
    app.appendChild(opts);

    if (t.kind === "pair") {
      app.appendChild(el("div", "note",
        "如果兩張都不像，請選「兩個都不像」，不要勉強挑一個。"));
    }
    shownAt = performance.now();
  }

  function answer(optionIndex, label) {
    var item = order[index];
    var t = item.trial;
    var rec = {
      id: t.id,
      section: t.section,
      kind: t.kind,
      option_index: optionIndex,
      option_label: label,
      flipped: item.flipped,
      ms: Math.round(performance.now() - shownAt)
    };
    if (t.kind === "pair") {
      rec.left = item.flipped ? t.b : t.a;
      rec.right = item.flipped ? t.a : t.b;
      // Resolve the click back to the stimulus, so "left" never has to be
      // decoded later against a randomisation nobody wrote down.
      if (optionIndex === 0) rec.chose = rec.left;
      else if (optionIndex === 1) rec.chose = rec.right;
      else rec.chose = optionIndex === 2 ? "tie" : "neither";
    } else {
      rec.image = t.image;
      rec.chose = label;
    }
    answers.push(rec);
    next();
  }

  function next() {
    index += 1;
    if (index >= order.length) finish();
    else render();
  }

  function finish() {
    app.innerHTML = "";
    app.appendChild(el("p", "eyebrow", "完成"));
    app.appendChild(el("h1", null, "謝謝，做完了"));
    var status = el("p", "lede", "正在儲存…");
    app.appendChild(status);

    var result = {
      session: sessionId,
      finished_at: new Date().toISOString(),
      total_ms: answers.reduce(function (s, a) { return s + a.ms; }, 0),
      answers: answers
    };

    var pre = el("pre", "result", JSON.stringify(result, null, 1));
    app.appendChild(el("p", "note",
      "如果上面顯示儲存失敗，請把下面這段文字整個複製傳回去。"));
    app.appendChild(pre);

    if (window.claude && window.claude.use) {
      window.claude.use("db").then(function (db) {
        if (!db) {
          status.textContent = "這個裝置無法自動儲存，請複製下面的文字傳回去。";
          return;
        }
        return db.doc("sessions/" + sessionId).set(result).then(function () {
          status.textContent = "已儲存。可以關掉這個頁面了。";
          status.className = "lede saved";
        });
      }).catch(function () {
        status.textContent = "自動儲存失敗，請複製下面的文字傳回去。";
      });
    } else {
      status.textContent = "請把下面的文字整個複製傳回去。";
    }
  }

  try {
    intro();
  } catch (err) {
    app.textContent = "頁面載入失敗：" + err.message;
  }
})();
</script>
"""


if __name__ == "__main__":
    main()
