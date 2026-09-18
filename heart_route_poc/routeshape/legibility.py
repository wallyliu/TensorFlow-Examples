"""
What a street network can and cannot draw, before any route is fitted.

POC 37 lost three OpenMoji shapes - fish, house, plane - whose outlines are
plainly better than the hand-drawn ones and whose routes were named by nobody.
Every one of them passed the excursion limit. Looking at the routes, the reason
is the same in all three: the interior detail is finer than the street grid, so
it survives in the OUTLINE and is ground off in the ROUTE, leaving a polygon
with no identity.

BACKLOG 43 records a failed attempt to catch that - smallest feature thickness
over street scale - which measured the out-and-back connectors instead of the
features, because a line ridden out and back has zero thickness by definition.
The gear scored 7 m and three of three raters named it.

THE RIGHT OBJECT IS NOT THICKNESS, IT IS RESOLUTION. A route is a walk on a
graph whose junctions sit about one street apart, so whatever the drawing says,
the route can only put a corner every `street_m`. Resample the template at that
spacing and the gap between the two is the best any route could possibly do -
a FLOOR on excursion that depends only on the drawing, the width and the city,
and needs no network and no fitting.

That is the standard reading of scale space applied to this problem: a feature
smaller than the sampling scale cannot be recovered, and the amount of the
figure that lives below the scale is measurable. `vanishing` says WHERE it
lives, so a drawing can be fixed rather than only rejected.

Nothing here is calibrated against raters yet - see poc40_legibility.
"""

from __future__ import annotations

import numpy as np

from routeshape.shapes.library import resample_by_arclength


def _closed(points: np.ndarray) -> np.ndarray:
    return np.vstack([points, points[:1]])


def _point_to_polyline(points: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Distance from each point to a closed polyline, segment by segment."""
    a, b = poly[:-1], poly[1:]
    ab = b - a
    denom = np.einsum("ij,ij->i", ab, ab)
    denom[denom == 0] = 1.0
    ap = points[:, None, :] - a[None, :, :]
    t = np.clip(np.einsum("ijk,jk->ij", ap, ab) / denom, 0.0, 1.0)
    closest = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    return np.hypot(*(points[:, None, :] - closest).transpose(2, 0, 1)).min(axis=1)


def sampled(shape: str, width_m: float, street_m: float,
            dense: int = 4000) -> tuple[np.ndarray, np.ndarray]:
    """(the drawing at this size, the most a route could resolve of it).

    The second is the template resampled at one point per street, which is the
    best case: every corner landing exactly where the drawing wants it.
    """
    template = resample_by_arclength(shape, dense) * width_m
    perimeter = float(np.hypot(*np.diff(_closed(template), axis=0).T).sum())
    n = max(4, int(round(perimeter / street_m)))
    return template, resample_by_arclength(shape, n) * width_m


def resolution_error(shape: str, width_m: float, street_m: float) -> float:
    """The floor on excursion for this drawing at this size, over width.

    Comparable with `metrics.excursion` on purpose: both are a worst-case gap
    from the template as a fraction of the drawing's width, so a shape whose
    floor is already 0.06 cannot be expected to come in under an 0.08 limit
    with anything to spare.
    """
    template, coarse = sampled(shape, width_m, street_m)
    gap = _point_to_polyline(template, _closed(coarse))
    width = float(max(template.max(axis=0) - template.min(axis=0)))
    return float(gap.max() / width) if width > 0 else float("inf")


def vanishing(shape: str, width_m: float, street_m: float,
              regions: int = 48) -> np.ndarray:
    """Per arc of the outline, how much of it the street scale cannot hold.

    Same units as `resolution_error`, one number per equal arc-length region,
    so the answer is "the tail and the left wing" rather than only "too fine".
    """
    template, coarse = sampled(shape, width_m, street_m)
    gap = _point_to_polyline(template, _closed(coarse))
    width = float(max(template.max(axis=0) - template.min(axis=0)))
    span = len(template) // regions
    return np.array([gap[i * span:(i + 1) * span].max() / width
                     for i in range(regions)])
