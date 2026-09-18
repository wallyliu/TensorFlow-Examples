"""
Type a word, get a shape - from every emoji the font can draw, not a curated list.

The tracer in `shapes.emoji` was never tied to the 28 subjects in its PACK: it
takes any character the font has a glyph for. What was missing is the step from
a word a rider types to that character, and this is that step.

WHERE THE WORDS COME FROM. Unicode's own CLDR annotations, which give every
emoji a short name and a list of keywords in a hundred-odd languages. Traditional
Chinese and English are pulled here. That is the difference between a feature
and a demo: a hand-written table of a hundred nouns would cover whatever I
happened to think of, and CLDR covers what the Unicode consortium and its
Chinese-language contributors thought of.

WHAT GETS INTO THE INDEX. Only emoji that survive the whole pipeline: the font
has the glyph, the tracer produces a curve, `describe.check` passes it (no
self-crossings, sane vertex count and aspect), and `feasibility` can size it.
A rider typing 狗 must not be able to reach a crash, so the filtering happens
once at build time rather than per request.

WHAT THE INDEX DOES NOT PROMISE is that the route will be recognisable. Every
shape on the page went through rater rounds and POC 39 found the DRAWING is the
only thing that predicts naming; an emoji nobody has rated gets no number and
the page says so. This widens what a rider can ask for, not what is known to
work.

Build:  python -m routeshape.shapes.emoji_index
Out:    routeshape/shapes/emoji_index.json
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE / "emoji_index.json"
CLDR = ("https://raw.githubusercontent.com/unicode-org/cldr/main"
        "/common/annotations/{tag}.xml")
FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
# The blocks with pictures in them. Dingbats and the arrows below 0x2600 are
# mostly symbols a route cannot say anything with.
BLOCKS = ((0x1F300, 0x1F6FF), (0x1F900, 0x1FAFF), (0x2600, 0x27BF))
MAX_HITS = 8

_loaded: dict | None = None


# ---------------------------------------------------------------------------
# building
# ---------------------------------------------------------------------------

def _annotations(tag: str) -> tuple[dict, dict]:
    """(short name per character, keywords per character) from CLDR."""
    import urllib.request

    with urllib.request.urlopen(CLDR.format(tag=tag), timeout=60) as r:
        body = r.read().decode("utf-8")
    names, keywords = {}, {}
    for cp, attrs, text in re.findall(
            r'<annotation cp="([^"]+)"([^>]*)>([^<]+)</annotation>', body):
        if 'type="tts"' in attrs:
            names[cp] = text.strip()
        else:
            keywords[cp] = [w.strip() for w in text.split("|") if w.strip()]
    return names, keywords


def _drawable() -> list[str]:
    """Every character in the blocks that the emoji font actually has."""
    from matplotlib.ft2font import FT2Font

    font = FT2Font(FONT)
    return [chr(cp) for lo, hi in BLOCKS for cp in range(lo, hi + 1)
            if font.get_char_index(cp)]


def build() -> dict:
    import routeshape.describe as describe
    import routeshape.feasibility as rf
    import routeshape.shapes.emoji as emoji
    import routeshape.shapes.library as sl

    zh_names, zh_words = _annotations("zh_Hant")
    en_names, en_words = _annotations("en")
    rows, refused = [], 0
    for ch in _drawable():
        if ch not in zh_names and ch not in en_names:
            continue
        try:
            points = emoji.outline(ch)
            if not describe.check(points).ok:
                refused += 1
                continue
            # Under its FINAL name, not a shared scratch one. `feasibility.n_min`
            # is lru_cached on the shape's name, so probing 1,266 emoji through
            # one name gave all of them the first one's answer - every row in
            # the first build read 68 contour points.
            probe = register_name(ch)
            sl.register(probe, points)
            n_min = rf.n_min(probe)
        except Exception:                                # noqa: BLE001
            refused += 1
            continue
        try:
            unicode_name = unicodedata.name(ch).title()
        except ValueError:
            unicode_name = ""
        rows.append({
            "c": ch,
            "n": zh_names.get(ch) or en_names.get(ch) or unicode_name,
            "k": sorted(set(zh_words.get(ch, []))),
            "e": sorted(set(en_words.get(ch, []) + [en_names.get(ch, "")]) - {""}),
            "m": int(n_min),
        })
    out = {"built_from": "Unicode CLDR annotations (zh_Hant, en), CC BY 4.0",
           "font": FONT, "count": len(rows), "refused": refused, "emoji": rows}
    INDEX.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# using
# ---------------------------------------------------------------------------

def load() -> dict:
    global _loaded
    if _loaded is None:
        _loaded = (json.loads(INDEX.read_text(encoding="utf-8"))
                   if INDEX.exists() else {"emoji": []})
    return _loaded


def find(query: str, limit: int = MAX_HITS) -> list[dict]:
    """Emoji matching a typed word, best first.

    Ranked rather than filtered, because a rider who types 狗 should get the dog
    before the guide dog and the hot dog, and 「rocket」 should not be beaten by
    「rocket ship」 on alphabetical order. The ladder is: the query IS the name,
    the name starts with it, the query is one of the keywords, the query is
    inside the name, the query is inside a keyword. Shorter names win ties,
    which is what puts 狗 above 導盲犬.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    # A character the rider pasted in outranks anything a word could match.
    direct = [row for row in load()["emoji"] if row["c"] == q or row["c"] == query.strip()]
    if direct:
        return direct[:limit]

    hits = []
    for row in load()["emoji"]:
        name = row["n"].lower()
        words = [w.lower() for w in row["k"] + row["e"]]
        if q == name:
            score = 0
        elif name.startswith(q):
            score = 1
        elif q in words:
            score = 2
        elif q in name:
            score = 3
        elif any(q in w for w in words):
            score = 4
        else:
            continue
        hits.append((score, len(row["n"]), row))
    hits.sort(key=lambda h: (h[0], h[1]))
    return [row for _, _, row in hits[:limit]]


def register_name(char: str) -> str:
    """The shape-library name one emoji goes in under."""
    return "q_" + "_".join(f"{ord(c):X}" for c in char)


def register(char: str) -> str | None:
    """Put one emoji in the shape library and return the name it went in under."""
    import routeshape.shapes.emoji as emoji
    import routeshape.shapes.library as sl

    name = register_name(char)
    if name in sl.SHAPES:
        return name
    try:
        sl.register(name, emoji.outline(char))
    except Exception:                                    # noqa: BLE001
        return None
    return name


def label(char: str) -> str:
    for row in load()["emoji"]:
        if row["c"] == char:
            return row["n"]
    return char


if __name__ == "__main__":
    import time

    t0 = time.time()
    out = build()
    print(f"{out['count']} emoji indexed, {out['refused']} refused, "
          f"{INDEX.stat().st_size / 1000:.0f} KB, {time.time() - t0:.0f}s")
