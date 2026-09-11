"""
A single-stroke font: each letter is a few open polylines with no thickness.

The outline font in `multi_contour.text_contours` traces both edges of every
letter stroke, which is what a printed letter is. A rider does not need both
edges - one line down the middle reads as the letter just as well, and it is
what most people picture when they imagine "drawing a word on the map".

Geometry only, in a unit box: x from 0, y from 0 (baseline) to 1 (cap height).
Circular letters are generated parametrically so they stay smooth at any n.

POC 12 measured this against the outline font and it lost on both counts: no
shorter (a line with no thickness is ridden twice, which is what an outline
costs anyway) and less legible (every part of the drawing being a thin line,
the connectors between strokes read as strokes). Kept because the choice is
the rider's to make.
"""

from __future__ import annotations

import numpy as np

W = 0.68          # advance width of a glyph, before letter spacing
SPACING = 0.22    # gap between glyphs


def _arc(cx, cy, rx, ry, a0, a1, n=24):
    t = np.linspace(np.radians(a0), np.radians(a1), n)
    return np.column_stack([cx + rx * np.cos(t), cy + ry * np.sin(t)])


def _oval(cx=0.34, cy=0.5, rx=0.34, ry=0.5, n=40):
    return _arc(cx, cy, rx, ry, 0, 360, n)


def _line(*pts):
    return np.array(pts, dtype=float)


GLYPHS: dict[str, list[np.ndarray]] = {
    " ": [],
    "A": [_line((0, 0), (0.34, 1), (0.68, 0)), _line((0.12, 0.36), (0.56, 0.36))],
    "B": [_line((0, 0), (0, 1), (0.42, 1)),
          np.vstack([_arc(0.42, 0.75, 0.24, 0.25, 90, -90), _line((0, 0.5))]),
          np.vstack([_line((0, 0.5), (0.42, 0.5)), _arc(0.42, 0.25, 0.26, 0.25, 90, -90),
                     _line((0, 0))])],
    "C": [_arc(0.36, 0.5, 0.32, 0.5, 55, 305)],
    "D": [np.vstack([_line((0, 0), (0, 1), (0.3, 1)), _arc(0.3, 0.5, 0.38, 0.5, 90, -90),
                     _line((0, 0))])],
    "E": [_line((0.64, 1), (0, 1), (0, 0), (0.64, 0)), _line((0, 0.5), (0.48, 0.5))],
    "F": [_line((0.64, 1), (0, 1), (0, 0)), _line((0, 0.52), (0.46, 0.52))],
    "G": [np.vstack([_arc(0.36, 0.5, 0.32, 0.5, 55, 300), _line((0.68, 0.4), (0.4, 0.4))])],
    "H": [_line((0, 0), (0, 1)), _line((0.64, 0), (0.64, 1)), _line((0, 0.5), (0.64, 0.5))],
    "I": [_line((0.1, 0), (0.54, 0)), _line((0.32, 0), (0.32, 1)), _line((0.1, 1), (0.54, 1))],
    "J": [np.vstack([_line((0.62, 1), (0.62, 0.22)), _arc(0.36, 0.22, 0.26, 0.22, 0, -180)])],
    "K": [_line((0, 0), (0, 1)), _line((0.62, 1), (0, 0.42)), _line((0.2, 0.58), (0.64, 0))],
    "L": [_line((0, 1), (0, 0), (0.6, 0))],
    "M": [_line((0, 0), (0, 1), (0.34, 0.34), (0.68, 1), (0.68, 0))],
    "N": [_line((0, 0), (0, 1), (0.64, 0), (0.64, 1))],
    "O": [_oval()],
    "P": [np.vstack([_line((0, 0), (0, 1), (0.4, 1)), _arc(0.4, 0.74, 0.26, 0.26, 90, -90),
                     _line((0, 0.48))])],
    "Q": [_oval(), _line((0.42, 0.26), (0.7, -0.04))],
    "R": [np.vstack([_line((0, 0), (0, 1), (0.4, 1)), _arc(0.4, 0.74, 0.26, 0.26, 90, -90),
                     _line((0, 0.48))]),
          _line((0.3, 0.48), (0.66, 0))],
    "S": [np.vstack([_arc(0.34, 0.74, 0.28, 0.26, 25, 270), _arc(0.34, 0.22, 0.28, 0.26, 90, -160)])],
    "T": [_line((0, 1), (0.64, 1)), _line((0.32, 1), (0.32, 0))],
    "U": [np.vstack([_line((0, 1), (0, 0.28)), _arc(0.32, 0.28, 0.32, 0.28, 180, 360),
                     _line((0.64, 1))])],
    "V": [_line((0, 1), (0.32, 0), (0.64, 1))],
    "W": [_line((0, 1), (0.15, 0), (0.34, 0.68), (0.53, 0), (0.68, 1))],
    "X": [_line((0, 0), (0.64, 1)), _line((0, 1), (0.64, 0))],
    "Y": [_line((0, 1), (0.32, 0.52), (0.64, 1)), _line((0.32, 0.52), (0.32, 0))],
    "Z": [_line((0, 1), (0.64, 1), (0, 0), (0.64, 0))],
}


def strokes(text: str) -> list[np.ndarray]:
    """The word's centre lines, laid out left to right. Open polylines."""
    out, pen = [], 0.0
    for ch in text.upper():
        glyph = GLYPHS.get(ch)
        if glyph is None:
            raise KeyError(f"no single-stroke glyph for {ch!r}")
        for s in glyph:
            out.append(np.asarray(s, dtype=float) + np.array([pen, 0.0]))
        pen += W + SPACING
    return out


def stroke_to_contour(polyline: np.ndarray) -> np.ndarray:
    """
    An open line, as a closed contour of zero area: out and back.

    This is the whole trick that lets single-stroke text reuse the multi-contour
    machinery unchanged. A rider cannot lift the pen, so an open stroke is
    already ridden twice; writing it that way up front means `merge` sees only
    closed contours and needs no special case.
    """
    p = np.asarray(polyline, dtype=float)
    if len(p) < 2:
        return p
    return np.vstack([p, p[-2:0:-1]])
