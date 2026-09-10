"""
POC 5, step 3 - generate the labelling page from the selected pairs.

Kept as a generator rather than a hand-written HTML file so the page and the
analysis read the same `poc5_pairs.json`, and so regenerating the pairs cannot
silently leave the page showing stale shapes.

Run:  python poc5_build_page.py
Out:  poc5_labelling.html
"""

from pathlib import Path

PAIRS = Path(__file__).with_name("poc5_pairs.json")
OUT_HTML = Path(__file__).with_name("poc5_labelling.html")

PAGE = """<title>Which One Reads As A Heart</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@400;500&display=swap">
<style>
  :root {
    --paper: #eef1f4; --card: #ffffff; --ink: #14181d; --muted: #6b7580;
    --line: #ccd4dc; --accent: #1f6f9f; --accent-soft: #e3eef6; --stroke: #22282f;
    --sans: "IBM Plex Sans", system-ui, -apple-system, "Noto Sans TC", sans-serif;
    --serif: "IBM Plex Serif", Georgia, "Noto Serif TC", serif;
    --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
  }
  :root:not([data-theme="light"]) { }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #12161a; --card: #1a1f25; --ink: #e4e9ee; --muted: #8b959f;
      --line: #2b333b; --accent: #6db4de; --accent-soft: #1c2c38; --stroke: #dfe5ea;
    }
  }
  :root[data-theme="dark"] {
    --paper: #12161a; --card: #1a1f25; --ink: #e4e9ee; --muted: #8b959f;
    --line: #2b333b; --accent: #6db4de; --accent-soft: #1c2c38; --stroke: #dfe5ea;
  }

  body {
    background: var(--paper); color: var(--ink); font-family: var(--sans);
    padding-block: 28px 56px; padding-left: 20px; padding-right: 20px;
    line-height: 1.55;
  }
  .wrap { max-width: 1000px; margin: 0 auto; display: flex; flex-direction: column; gap: 26px; }

  .rail { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .rail h1 { font-family: var(--sans); font-size: 15px; font-weight: 600; letter-spacing: .01em; margin: 0; }
  .rail .count { font-family: var(--mono); font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .bar { height: 3px; background: var(--line); border-radius: 2px; overflow: hidden; }
  .bar > i { display: block; height: 100%; width: 0%; background: var(--accent); transition: width .25s ease; }

  .ask { font-family: var(--serif); font-size: clamp(22px, 3.4vw, 30px); font-weight: 500;
         margin: 0 0 10px; text-wrap: balance; }
  .hint { margin: 0; color: var(--muted); font-size: 13.5px; max-width: 76ch; }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }

  .pick { appearance: none; background: var(--card); border: 1px solid var(--line);
          border-radius: 4px; padding: 14px 14px 10px; cursor: pointer; display: flex;
          flex-direction: column; gap: 8px; color: inherit; font: inherit; }
  .pick:hover { border-color: var(--accent); }
  .pick:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .pick[data-chosen="1"] { border-color: var(--accent); background: var(--accent-soft); }
  .pick svg { width: 100%; height: auto; display: block; }
  .pick svg path { fill: none; stroke: var(--stroke); stroke-width: 1.05;
                   stroke-linejoin: round; stroke-linecap: round; }
  .pick .side { font-family: var(--mono); font-size: 12px; color: var(--muted);
                display: flex; justify-content: space-between; }

  .tie { align-self: center; appearance: none; background: none; border: 1px solid var(--line);
         border-radius: 999px; padding: 7px 18px; font-family: var(--mono); font-size: 12.5px;
         color: var(--muted); cursor: pointer; }
  .tie:hover { border-color: var(--accent); color: var(--accent); }
  .tie:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .note { border-left: 2px solid var(--line); padding-left: 14px; color: var(--muted);
          font-size: 13.5px; max-width: 62ch; }
  .note b { color: var(--ink); font-weight: 600; }
  .warn { border-left-color: var(--accent); }

  .done { background: var(--card); border: 1px solid var(--line); border-radius: 4px; padding: 26px; }
  .done h2 { font-family: var(--serif); font-size: 24px; margin: 0 0 10px; font-weight: 500; }
  .done dl { display: grid; grid-template-columns: auto 1fr; gap: 6px 18px; margin: 18px 0 0;
             font-family: var(--mono); font-size: 13px; font-variant-numeric: tabular-nums; }
  .done dt { color: var(--muted); } .done dd { margin: 0; }
  textarea { width: 100%; height: 130px; margin-top: 18px; font-family: var(--mono); font-size: 11px;
             background: var(--paper); color: var(--ink); border: 1px solid var(--line);
             border-radius: 4px; padding: 10px; }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap">
  <div>
    <div class="rail">
      <h1>心形路線 · 人工判斷</h1>
      <span class="count" id="count">準備中…</span>
    </div>
    <div class="bar" style="margin-top:10px"><i id="prog"></i></div>
  </div>

  <div id="stage">
    <p class="ask" id="ask">哪一條路線比較像心形？</p>
    <p class="hint">兩張圖都是真實或變形過的走路路線，已經把位置和大小正規化。憑第一眼直覺選就好。鍵盤：<b>←</b> 選左、<b>→</b> 選右、<b>空白鍵</b> 差不多。</p>
    <div class="grid" style="margin-top:22px">
      <button class="pick" id="left" type="button">
        <svg viewBox="0 0 100 100" aria-label="左邊的路線"><path id="pathL" d=""></path></svg>
        <span class="side"><span>左</span><span>←</span></span>
      </button>
      <button class="pick" id="right" type="button">
        <svg viewBox="0 0 100 100" aria-label="右邊的路線"><path id="pathR" d=""></path></svg>
        <span class="side"><span>右</span><span>→</span></span>
      </button>
    </div>
    <div style="display:flex; justify-content:center; margin-top:18px">
      <button class="tie" id="tie" type="button">兩個差不多</button>
    </div>
  </div>

  <p class="note" id="status">這 25 題裡有幾題會重複出現，那是用來量你自己判斷的一致性 —— 沒有這個數字，就無法分辨「指標不準」和「人本來就會前後不一」。左右邊也是隨機排的。</p>
</div>

<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById("payload").textContent);
  var trials = data.trials, shapes = data.shapes;
  var answers = {}, index = 0, db = null, locked = false;

  var el = {
    count: document.getElementById("count"), prog: document.getElementById("prog"),
    stage: document.getElementById("stage"), status: document.getElementById("status"),
    left: document.getElementById("left"), right: document.getElementById("right"),
    tie: document.getElementById("tie"),
    pathL: document.getElementById("pathL"), pathR: document.getElementById("pathR")
  };

  function render() {
    while (index < trials.length && answers[trials[index].pair_id]) index++;
    var answered = Object.keys(answers).length;
    el.count.textContent = answered + " / " + trials.length;
    el.prog.style.width = (answered / trials.length * 100) + "%";

    if (index >= trials.length) { finish(); return; }
    var t = trials[index];
    el.pathL.setAttribute("d", shapes[t.items[0]]);
    el.pathR.setAttribute("d", shapes[t.items[1]]);
    el.left.dataset.chosen = "0"; el.right.dataset.chosen = "0";
    locked = false;
  }

  function choose(which) {
    if (locked || index >= trials.length) return;
    locked = true;
    var t = trials[index];
    var picked = which === "tie" ? "tie" : t.items[which === "left" ? 0 : 1];
    if (which !== "tie") document.getElementById(which).dataset.chosen = "1";

    var record = {
      pair_id: t.pair_id, left: t.items[0], right: t.items[1],
      chose: picked, repeat_of: t.repeat_of, at: new Date().toISOString()
    };
    answers[t.pair_id] = record;
    if (db) db.doc("labels/" + t.pair_id).set(record).catch(function () {
      el.status.className = "note warn";
      el.status.innerHTML = "<b>這一題沒能存到伺服器。</b>做完後請把最下面的文字方塊整段複製給我。";
    });
    setTimeout(function () { index++; render(); }, which === "tie" ? 0 : 160);
  }

  function finish() {
    var vals = Object.keys(answers).map(function (k) { return answers[k]; });
    var ties = vals.filter(function (a) { return a.chose === "tie"; }).length;
    el.stage.innerHTML =
      '<div class="done"><h2>做完了，謝謝</h2>' +
      '<p style="margin:0;color:var(--muted);max-width:62ch">這是這個專案第一次有真正的 ground truth。' +
      '接下來我會用它算四個指標各自跟你的一致率，並以你自己的重複題一致性當作上限基準。</p>' +
      '<dl><dt>已完成</dt><dd>' + vals.length + ' 題</dd>' +
      '<dt>判定差不多</dt><dd>' + ties + ' 題</dd>' +
      '<dt>儲存狀態</dt><dd>' + (db ? "已存到伺服器" : "未連線，請複製下方內容") + '</dd></dl>' +
      '<textarea readonly id="dump"></textarea></div>';
    document.getElementById("dump").value = JSON.stringify(vals);
    el.status.textContent = "如果想重做某一題，重新整理後它會從未作答的地方繼續；已作答的題目會被跳過。";
  }

  el.left.addEventListener("click", function () { choose("left"); });
  el.right.addEventListener("click", function () { choose("right"); });
  el.tie.addEventListener("click", function () { choose("tie"); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") { e.preventDefault(); choose("left"); }
    else if (e.key === "ArrowRight") { e.preventDefault(); choose("right"); }
    else if (e.key === " ") { e.preventDefault(); choose("tie"); }
  });

  render();  // paint immediately; db only resumes prior answers

  (window.claude && window.claude.use ? window.claude.use("db") : Promise.resolve(null))
    .then(function (store) {
      if (!store) {
        el.status.className = "note warn";
        el.status.innerHTML = "<b>這一份沒有連上儲存空間</b>，答案只留在這個分頁。做完請把文字方塊整段複製給我。";
        return;
      }
      db = store;
      return db.collection("labels").get().then(function (snap) {
        snap.docs.forEach(function (d) { if (d.exists) answers[d.id] = d.data(); });
        index = 0; render();
      });
    })
    .catch(function () { /* offline is already the rendered state */ });
})();
</script>
"""


def main() -> None:
    payload = PAIRS.read_text()
    # Guard the JSON against closing the script element it lives in.
    payload = payload.replace("</", "<\\/")
    OUT_HTML.write_text(PAGE.replace("__PAYLOAD__", payload))
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
