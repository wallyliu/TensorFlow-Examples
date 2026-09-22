"""Turning a distance into a shape size, and refusing when it cannot be done.

No map is involved anywhere in this file, which is the point of the derivation:
the perimeter cancels out of D_min = n_min x street_scale x detour, so a
shape's floor depends on how much detail it carries and how far apart the
streets are, and on nothing else.

The round trip is the test that matters. `width_for` solves a quadratic because
the detour is itself a function of width; dividing by a fixed detour is what
made a 50 km request come back 22 km long, and that bug would survive any test
that only checked the function ran.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routeshape import feasibility as rf
from routeshape.shapes.library import SHAPES

BUILTIN = ("heart", "star5", "crescent", "triangle", "trex")


class Sizing(unittest.TestCase):
    def test_width_for_round_trips_through_the_distance_model(self):
        """Size to a target, then predict the distance back: they must agree.

        P.b.w^2 + P.a.w - T = 0 solved for w, then P x w x detour(w) evaluated -
        if the solver and the predictor ever disagree, the page promises one
        number and the rider gets another.
        """
        for shape in BUILTIN:
            for target in (10.0, 30.0, 50.0, 100.0):
                with self.subTest(shape=shape, target=target):
                    width = rf.width_for(shape, target)
                    predicted = (rf.perimeter(shape) * width
                                 * rf.detour_for(width) / 1000.0)
                    self.assertAlmostEqual(predicted, target, places=6)

    def test_width_for_honours_a_local_street_scale(self):
        """A sparse city needs a physically bigger shape to draw the same figure."""
        taipei = rf.width_for("heart", 30.0, street_scale_m=280.0)
        keelung = rf.width_for("heart", 30.0, street_scale_m=439.0)
        self.assertLess(keelung, taipei)   # same ride, more detour, so less shape

    def test_a_longer_ride_draws_a_bigger_shape(self):
        widths = [rf.width_for("heart", km) for km in (10.0, 30.0, 50.0, 100.0)]
        self.assertEqual(widths, sorted(widths))

    def test_detour_grows_with_size_and_with_sparseness(self):
        """POC 25: it is not the constant 1.25 the early POCs assumed."""
        self.assertLess(rf.detour_for(2000.0, 280.0), rf.detour_for(12000.0, 280.0))
        self.assertLess(rf.detour_for(5000.0, 142.0), rf.detour_for(5000.0, 280.0))

    def test_detour_matches_the_published_coefficients(self):
        width_m, scale_m = 5000.0, 280.0
        expected = (rf.DETOUR_INTERCEPT
                    + rf.DETOUR_PER_KM * width_m / 1000.0
                    + rf.DETOUR_PER_SCALE_M * scale_m)
        self.assertAlmostEqual(rf.detour_for(width_m, scale_m), expected, places=9)


class Floors(unittest.TestCase):
    def test_a_more_detailed_shape_needs_a_longer_ride(self):
        """n_min is the whole story: a triangle is cheaper than a dinosaur."""
        self.assertLess(rf.min_distance_km("triangle"), rf.min_distance_km("trex"))

    def test_the_floor_follows_n_min_across_the_whole_library(self):
        ordered = sorted(SHAPES, key=rf.n_min)
        floors = [rf.min_distance_km(s) for s in ordered]
        # Not strictly sorted - perimeter enters through the detour - but the
        # rank correlation has to be overwhelming or n_min is not the driver.
        # `SHAPES` here is the five parametric ones; the packs are installed by
        # the server, and test_shapes.py covers the full library.
        inversions = sum(1 for a, b in zip(floors, floors[1:]) if a > b)
        self.assertLessEqual(inversions, max(1, len(floors) // 4))

    def test_a_sparse_city_raises_the_floor(self):
        self.assertGreater(rf.min_distance_km("heart", "bike", 439.0),
                           rf.min_distance_km("heart", "bike", 280.0))

    def test_n_min_is_stable_and_bounded(self):
        for shape in SHAPES:
            with self.subTest(shape=shape):
                n = rf.n_min(shape)
                self.assertGreaterEqual(n, 4)
                self.assertLessEqual(n, 400)
                self.assertEqual(n, rf.n_min(shape))      # cached, deterministic

    def test_sampling_loss_falls_as_points_are_added(self):
        """The curve n_min reads. Noisy point to point, but it has to decay."""
        coarse = rf.sampling_loss("trex", 8)
        fine = rf.sampling_loss("trex", 200)
        self.assertLess(fine, coarse)
        self.assertLess(fine, rf.SAMPLING_TOLERANCE)


class Planning(unittest.TestCase):
    def test_below_the_floor_is_refused_with_the_number(self):
        """Never a bare 'not available' - the refusal carries what is needed."""
        floor = rf.min_distance_km("trex")
        p = rf.plan("trex", floor * 0.5)
        self.assertFalse(p.feasible)
        self.assertAlmostEqual(p.min_km, floor, places=6)
        self.assertIn(f"{floor:.1f}", p.reason)
        self.assertIsNone(p.width_m)
        self.assertIsNone(p.points)

    def test_just_above_the_floor_is_accepted(self):
        floor = rf.min_distance_km("trex")
        p = rf.plan("trex", floor * 1.01)
        self.assertTrue(p.feasible)
        self.assertIsNotNone(p.width_m)
        self.assertGreaterEqual(p.points, rf.n_min("trex"))

    def test_the_predicted_range_brackets_the_prediction(self):
        p = rf.plan("heart", 30.0)
        low, high = p.range_km
        self.assertLess(low, p.predicted_km)
        self.assertGreater(high, p.predicted_km)
        self.assertGreater(low, 0.0)

    def test_contour_points_sit_inside_the_window(self):
        """From n_min (enough to be the shape) to one point per street scale."""
        for shape in BUILTIN:
            for km in (30.0, 100.0):
                with self.subTest(shape=shape, km=km):
                    width = rf.width_for(shape, km)
                    n = rf.contour_points(shape, width)
                    cap = int(rf.perimeter(shape) * width / rf.MODES["bike"]["street_scale_m"])
                    self.assertGreaterEqual(n, rf.n_min(shape))
                    self.assertLessEqual(n, max(cap, rf.n_min(shape)))

    def test_every_shape_is_feasible_at_some_distance(self):
        for shape in SHAPES:
            with self.subTest(shape=shape):
                floor = rf.min_distance_km(shape)
                self.assertTrue(rf.plan(shape, floor * 1.05).feasible)

    def test_feasible_shapes_puts_the_possible_ones_first(self):
        plans = rf.feasible_shapes(20.0)
        flags = [p.feasible for p in plans]
        self.assertEqual(flags, sorted(flags, reverse=True))


if __name__ == "__main__":
    unittest.main()
