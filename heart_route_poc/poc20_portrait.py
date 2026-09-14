"""
Is a portrait drawable? Measuring the Mona Lisa, or rather a trace of her.

The user asked, half-joking. The answer is a number, and getting it needs one
honest caveat stated first: the image arrived in conversation rather than as a
file, so nothing here is edge-detected from the painting. These contours are
MY TRACE of what I can see - proportions eyeballed from the reproduction. That
is enough for a feasibility estimate, which is an order-of-magnitude question,
and not enough to call the result "the Mona Lisa's n_min".

Two versions, because they answer different questions.

  silhouette  head, hair, shoulders, arms, the block of the body. One closed
              curve, no interior. This is what a route can most easily be.
  lineart     the same plus the contours that make it HER: the face oval, both
              eyes, the nose, the mouth, the neckline, the hands.

The split matters more than either number. A portrait is recognisable by its
interior, and almost all of that interior is TONE, not line - the smile is a
shadow at the corner of the mouth, not a stroke. A silhouette of a seated woman
with long hair is any seated woman with long hair. So the honest question is
not "how many points does the outline need" but "does the outline carry the
identity at all", and for a painting the answer is mostly no.

Run:  python poc20_portrait.py
Out:  poc20_portrait.png, poc20_portrait.json
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import route_feasibility as rf
from multi_contour import densify, merge
from poc11_onestroke import n_min_curve, perimeter
from stroke_font import stroke_to_contour

# Traced in the reproduction's pixel frame: x right, y DOWN from the top edge,
# on a 960 x 1443 image. Flipped to y-up below.
SILHOUETTE = [
    (480, 150), (545, 172), (600, 250), (636, 400), (645, 560), (660, 700),
    (706, 762), (800, 800), (868, 900), (898, 1050), (905, 1250), (900, 1440),
    (150, 1440), (120, 1250), (110, 1050), (140, 900), (232, 800), (300, 742),
    (320, 600), (310, 430), (342, 278), (402, 176),
]
FACE = [
    (480, 190), (528, 218), (556, 300), (564, 388), (548, 462), (508, 512),
    (466, 522), (422, 486), (394, 420), (384, 322), (398, 236), (436, 200),
]
EYE_L = [(396, 322), (414, 308), (438, 310), (450, 324), (432, 336), (408, 334)]
EYE_R = [(498, 316), (518, 304), (542, 308), (552, 322), (532, 332), (510, 330)]
NOSE = [(470, 332), (460, 384), (452, 414), (470, 428), (496, 418)]          # open
MOUTH = [(432, 458), (470, 448), (512, 452), (538, 462), (498, 478), (452, 476)]
NECKLINE = [(352, 706), (420, 754), (492, 768), (566, 740), (608, 700)]      # open
HANDS = [
    (338, 1152), (392, 1114), (466, 1108), (528, 1140), (566, 1196),
    (524, 1238), (438, 1246), (362, 1214),
]

OUT_PNG = Path(__file__).with_name("poc20_portrait.png")
OUT_JSON = Path(__file__).with_name("poc20_portrait.json")


def closed(points) -> np.ndarray:
    """Pixel coordinates (y down) to a closed contour in y-up space."""
    a = np.array(points, dtype=float)
    return np.column_stack([a[:, 0], -a[:, 1]])


def open_stroke(points) -> np.ndarray:
    """An open line, as the zero-area contour the merger understands."""
    return stroke_to_contour(closed(points))


VERSIONS = {
    "silhouette": [closed(SILHOUETTE)],
    "lineart": [closed(SILHOUETTE), closed(FACE), closed(EYE_L), closed(EYE_R),
                open_stroke(NOSE), closed(MOUTH), open_stroke(NECKLINE),
                closed(HANDS)],
}


def main() -> None:
    cfg = rf.MODES["bike"]
    scale, detour = cfg["street_scale_m"], cfg["detour"]
    results = {}

    fig, axes = plt.subplots(1, len(VERSIONS), figsize=(5.2 * len(VERSIONS), 6.4))
    for ax, (name, contours) in zip(np.atleast_1d(axes), VERSIONS.items()):
        span = max(np.ptp(np.vstack(contours), axis=0))
        pieces = [densify(c, span * 0.004) for c in contours]
        curve, link_len, edges = merge(pieces, collinearity_weight=6.0)
        extent = curve.max(axis=0) - curve.min(axis=0)
        curve = (curve - curve.min(axis=0) - extent / 2) / extent[0]

        n = n_min_curve(curve, ceiling=1200)
        p = perimeter(curve)
        km = n * scale * detour / 1000.0
        width_km = n * scale / p / 1000.0
        results[name] = {
            "contours": len(contours), "links": len(edges), "n_min": n,
            "perimeter": p, "min_km": km, "width_km": width_km,
            "finest_feature_pct": scale / (width_km * 1000) * 100,
        }
        print(f"{name:<12}{len(contours):>3} contours  n_min {n:>5}  "
              f"{km:>7.1f} km  drawn {width_km:>5.1f} km wide  "
              f"finest detail {scale / (width_km * 1000) * 100:.1f}% of the picture")

        ax.plot(curve[:, 0], curve[:, 1], lw=1.0, color="#1a1a1a")
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(f"{name}\nn_min {n} · {km:.0f} km · {width_km:.0f} km wide",
                     fontsize=10)

    fig.suptitle("A trace of the Mona Lisa, as a route would have to draw her",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=130)
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT_PNG.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
