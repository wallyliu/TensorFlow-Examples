"""
Round two of the rater task: the same ladder, a different set of links.

Two changes from POC 13, and only two.

The dinosaur ladder is IDENTICAL - same eight trials under the same ids - so
three more raters pool directly with the first. That round produced four decided
judgements all in the same direction, which is the floor of what a sign test can
resolve (p = 0.125); pooling is the only way past it, and pooling requires the
stimuli not to move.

The text block is replaced. POC 13's rater read the outline route as "UT" and
said the links sat too close to the letters to tell them apart. So the new block
puts the nearest-point links against a rail - every letter dropping a stem to a
line below the word - and asks the same reading question. The old text stimuli
have already given their answer and are kept only as the comparison arm.

Run:  python poc14_build_task.py
Out:  poc14_task.html
"""

from __future__ import annotations

import json
import random

from poc13_build_task import PAIR_OPTIONS, RATE_OPTIONS, READ_OPTIONS, TEMPLATE, data_uri
from poc13_build_task import TRIALS as V1_TRIALS
from pathlib import Path

OUT = Path(__file__).with_name("poc14_task.html")

IMAGES = [
    "dino_clean", "dino_scrambled",
    "dino_L1_merged", "dino_L1_noise", "dino_L2_merged", "dino_L2_noise",
    "dino_L3_merged", "dino_L3_noise", "dino_L4_merged", "dino_L4_noise",
    "lit_outline_upright", "lit_outline_rail",
    "lit_stroke_upright", "lit_stroke_rail",
]

# Every dinosaur trial from round one, unchanged, so the two rounds pool.
DINO_TRIALS = [t for t in V1_TRIALS if t["section"] == "dino"]

READ_TRIALS = [
    {"id": "read_rail", "section": "read", "kind": "single",
     "image": "lit_outline_rail", "options": READ_OPTIONS,
     "prompt": "這條路線是照一個英文單字畫出來的。你覺得是哪一個？"},
    {"id": "read_mst", "section": "read", "kind": "single",
     "image": "lit_outline_upright", "options": READ_OPTIONS,
     "prompt": "這條路線是照一個英文單字畫出來的。你覺得是哪一個？"},
]

TEXT_TRIALS = [
    {"id": "rate_rail_outline", "section": "text", "kind": "single",
     "image": "lit_outline_rail", "options": RATE_OPTIONS,
     "prompt": "這條路線像不像英文字「LIT」？"},
    {"id": "rate_rail_stroke", "section": "text", "kind": "single",
     "image": "lit_stroke_rail", "options": RATE_OPTIONS,
     "prompt": "這條路線像不像英文字「LIT」？"},
    {"id": "pair_outline_link", "section": "text", "kind": "pair",
     "a": "lit_outline_upright", "b": "lit_outline_rail", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像英文字「LIT」？"},
    {"id": "pair_stroke_link", "section": "text", "kind": "pair",
     "a": "lit_stroke_upright", "b": "lit_stroke_rail", "options": PAIR_OPTIONS,
     "prompt": "哪一張比較像英文字「LIT」？"},
]


def main() -> None:
    # The two reading trials come first and their order is shuffled per build:
    # whichever route a rater sees first is the only one they see with no idea
    # what the word is, and that advantage should not always fall to the same
    # treatment.
    reads = READ_TRIALS[:]
    random.Random(14).shuffle(reads)
    trials = reads + DINO_TRIALS + TEXT_TRIALS

    images = {name: data_uri(name) for name in IMAGES}
    payload = json.dumps({"trials": trials, "images": images, "version": "v2"},
                         ensure_ascii=False, separators=(",", ":"))
    html = TEMPLATE.replace("__PAYLOAD__", payload)
    # A distinct name, so round one and round two are told apart in a gallery
    # that shows only titles.
    marker = "<title>這些路線看起來像什麼</title>"
    assert marker in html, "title marker moved; fix this before publishing"
    html = html.replace(marker, "<title>連接線會不會讓字讀不出來</title>")
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.name}: {len(trials)} trials "
          f"({len(DINO_TRIALS)} pooled from round one), {len(images)} images, "
          f"{OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
