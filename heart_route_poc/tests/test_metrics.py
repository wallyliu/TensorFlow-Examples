"""The shape metrics, tested on their invariants rather than on stored numbers.

`shape_distance` is the search's objective function: every placement in the
city is ranked by it. What it PROMISES is that position, size, orientation,
where the curve starts and which way it is traversed all mean nothing, and that
form means everything. Those are properties, and a property is testable without
knowing what the function returned yesterday.

This matters more than the usual coverage argument. The metric has been wrong
twice in this project - once comparing against the ROTATED reference, so no
comparison could see the rotation (POC 4), and once measuring excursion against
an upright template, which scored a correctly fitted Taiwan at 0.253 for its
tilt. Neither was a crash. Both were a number that looked reasonable.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routeshape.metrics import (alignment_angle, excursion, normalize_curve,
                                resample_closed, shape_distance)
from routeshape.wander import wander
from tests.gridfixture import circle, square


def rotate(xy: np.ndarray, deg: float) -> np.ndarray:
    t = np.radians(deg)
    r = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    return xy @ r.T


class ShapeDistance(unittest.TestCase):
    """RMS Procrustes distance, minimised over shift, direction and rotation."""

    def setUp(self):
        self.sq = square(1000.0, (0.0, 0.0), 64)
        self.ci = circle(500.0, (0.0, 0.0), 64)

    def test_identical_curves_are_zero(self):
        self.assertAlmostEqual(shape_distance(self.sq, self.sq), 0.0, places=6)

    def test_translation_does_not_matter(self):
        moved = self.sq + np.array([7000.0, -3000.0])
        self.assertAlmostEqual(shape_distance(self.sq, moved), 0.0, places=6)

    def test_scale_does_not_matter(self):
        self.assertAlmostEqual(shape_distance(self.sq, self.sq * 17.0), 0.0, places=6)

    def test_rotation_does_not_matter(self):
        # POC 5: a rater called rotated and upright hearts equally heart-like.
        for deg in (7.0, 45.0, 90.0, 180.0, 271.0):
            with self.subTest(deg=deg):
                self.assertAlmostEqual(
                    shape_distance(self.sq, rotate(self.sq, deg)), 0.0, places=5)

    def test_where_the_curve_starts_does_not_matter(self):
        for k in (1, 13, 37):
            with self.subTest(shift=k):
                self.assertAlmostEqual(
                    shape_distance(self.sq, np.roll(self.sq, k, axis=0)), 0.0, places=6)

    def test_direction_of_travel_does_not_matter(self):
        self.assertAlmostEqual(shape_distance(self.sq, self.sq[::-1]), 0.0, places=6)

    def test_different_forms_are_not_zero(self):
        self.assertGreater(shape_distance(self.sq, self.ci), 0.02)

    def test_symmetric(self):
        self.assertAlmostEqual(shape_distance(self.sq, self.ci),
                               shape_distance(self.ci, self.sq), places=6)

    def test_a_dented_square_is_closer_to_a_square_than_a_circle_is(self):
        dented = self.sq.copy()
        dented[10] += np.array([60.0, 60.0])
        self.assertLess(shape_distance(self.sq, dented),
                        shape_distance(self.sq, self.ci))

    def test_bigger_dent_scores_worse(self):
        previous = 0.0
        for push in (40.0, 120.0, 300.0):
            dented = self.sq.copy()
            dented[10] += np.array([push, push])
            here = shape_distance(self.sq, dented)
            self.assertGreater(here, previous)
            previous = here


class Normalisation(unittest.TestCase):
    def test_normalize_curve_centres_and_scales(self):
        out = normalize_curve(self.offset_square(), 256)
        self.assertEqual(out.shape, (256, 2))
        np.testing.assert_allclose(out.mean(axis=0), [0.0, 0.0], atol=1e-9)
        # Unit scale of some kind - the point is it no longer depends on input size.
        big = normalize_curve(self.offset_square() * 50.0, 256)
        np.testing.assert_allclose(out, big, atol=1e-9)

    def test_resample_closed_spaces_points_evenly(self):
        """Equal arc length along the polyline, so equal chords between samples.

        Fed a nine-point square the chords are NOT equal, and that is correct
        rather than a bug: a sample interval that crosses a corner covers the
        same arc length in a shorter straight line. Any input dense enough that
        corners fall between samples gives exactly equal spacing.
        """
        pts = resample_closed(square(1000.0, (0.0, 0.0), 1000), 400)
        closed = np.vstack([pts, pts[:1]])
        steps = np.hypot(*np.diff(closed, axis=0).T)
        self.assertLess(steps.std() / steps.mean(), 1e-9)

    def test_resample_closed_rejects_a_degenerate_curve(self):
        with self.assertRaises(ValueError):
            resample_closed(np.zeros((8, 2)), 64)

    @staticmethod
    def offset_square():
        return square(1000.0, (12345.0, -678.0), 64)


class AlignmentAngle(unittest.TestCase):
    """How far the finished route turned out to be from its template."""

    def test_recovers_a_known_rotation(self):
        template = square(1000.0, (0.0, 0.0), 256)
        for deg in (0.0, 30.0, 61.0):
            with self.subTest(deg=deg):
                got = alignment_angle(rotate(template, deg), template)
                # It answers how far to turn the route BACK, so a template
                # rotated by +deg wants -deg. A square is 90-degree symmetric,
                # so only congruence mod 90 can be asserted.
                off = (got + deg) % 90.0
                self.assertAlmostEqual(min(off, 90.0 - off), 0.0, delta=1.0)


class Excursion(unittest.TestCase):
    """The worst single stray, over the shape's width. A maximum, not a mean."""

    def setUp(self):
        self.template = square(1000.0, (0.0, 0.0), 512)

    def test_a_curve_on_its_template_barely_strays(self):
        self.assertLess(excursion(self.template, self.template), 0.01)

    def test_a_spur_costs_more_here_than_a_wobble_of_equal_shape_distance(self):
        """The property excursion exists for: it is a MAXIMUM, not an average.

        A rater looked at a perfect Taiwan with one straight bar shot across the
        bottom right and answered "cannot tell", naming the bar. `shape_distance`
        averages over the whole curve and so charges a localised spur and a
        diffuse wobble about the same; this has to charge the spur more.

        Tuned so the two defects have the SAME shape distance, which is the only
        way the comparison says anything.
        """
        spur = self.template.copy()
        spur[200:208] = spur[200:208] * 0.55            # an out-and-back inwards

        phase = np.linspace(0.0, 24 * np.pi, len(self.template))
        wobble = self.template + 119.0 * np.column_stack([np.sin(phase),
                                                          np.cos(phase)])

        self.assertAlmostEqual(shape_distance(spur, self.template),
                               shape_distance(wobble, self.template), delta=0.01)
        self.assertGreater(excursion(spur, self.template),
                           excursion(wobble, self.template) * 1.5)

    def test_scale_invariant(self):
        spur = self.template.copy()
        spur[200:206] = np.array([0.0, 0.0])
        near = excursion(spur, self.template)
        far = excursion(spur * 40.0, self.template * 40.0)
        self.assertAlmostEqual(near, far, places=6)

    def test_grows_with_the_stray(self):
        previous = 0.0
        for depth in (0.15, 0.35, 0.5):
            strayed = self.template.copy()
            strayed[200:206] = strayed[200:206] * (1.0 - depth)
            here = excursion(strayed, self.template)
            self.assertGreater(here, previous)
            previous = here


class Wander(unittest.TestCase):
    """arclength(route) / arclength(template) - 1, floored at zero."""

    def test_a_curve_on_its_template_does_not_wander(self):
        t = square(1000.0, (0.0, 0.0), 256)
        self.assertAlmostEqual(wander(t, t), 0.0, places=6)

    def test_a_longer_curve_wanders_by_the_length_ratio(self):
        t = square(1000.0, (0.0, 0.0), 256)
        self.assertAlmostEqual(wander(t * 1.5, t), 0.5, places=6)

    def test_floored_at_zero(self):
        t = square(1000.0, (0.0, 0.0), 256)
        self.assertGreaterEqual(wander(t * 0.5, t), 0.0)


if __name__ == "__main__":
    unittest.main()
