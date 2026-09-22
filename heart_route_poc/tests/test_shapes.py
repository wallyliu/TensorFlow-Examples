"""The shape library, over every drawing the server actually offers.

Every shape in this project - parametric, hand-drawn, traced off an emoji,
spelled out of letterforms - has to satisfy the same contract, because
everything downstream assumes it: ordered points, implicitly closed, centred on
the bounding box, width exactly 1.0. Only `width_m` at placement time sets size.

Traced shapes are where this has broken. OpenMoji's crab came back as a 23-point
blob because the tracer took only the largest filled path; the sauropod lost its
whole body to an `isclosed()` check; shading regions retraced the silhouette and
put 28 self-crossings on the snowman. None of those raised. They just produced a
curve, and the curve was wrong.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routeshape.shapes import multi_contour as mc
from routeshape.shapes import pack as shape_pack
from routeshape.shapes.library import SHAPES, register, resample_by_arclength

shape_pack.install()          # the hand-drawn pack, as the server installs it


class LibraryContract(unittest.TestCase):
    """What every shape promises, whatever drew it."""

    def test_every_shape_is_finite_ordered_and_closed_implicitly(self):
        for name in SHAPES:
            with self.subTest(shape=name):
                pts = resample_by_arclength(name, 256)
                self.assertEqual(pts.shape, (256, 2))
                self.assertTrue(np.isfinite(pts).all())
                # Implicitly closed: the last point must NOT repeat the first.
                self.assertGreater(float(np.hypot(*(pts[-1] - pts[0]))), 0.0)

    def test_every_shape_is_normalised_to_unit_width_and_centred(self):
        for name in SHAPES:
            with self.subTest(shape=name):
                # Dense, and with a tolerance: the extreme point of a shape
                # generally falls BETWEEN two samples, so a measured bounding
                # box is always a shade under the true one.
                pts = resample_by_arclength(name, 4000)
                lo, hi = pts.min(axis=0), pts.max(axis=0)
                self.assertAlmostEqual(float(hi[0] - lo[0]), 1.0, delta=0.01)
                self.assertAlmostEqual(float((hi[0] + lo[0]) / 2), 0.0, delta=0.01)
                self.assertAlmostEqual(float((hi[1] + lo[1]) / 2), 0.0, delta=0.01)

    def test_aspect_ratio_survives_normalisation(self):
        """Both axes divided by the SAME number, so proportions are the shape's."""
        for name in SHAPES:
            with self.subTest(shape=name):
                pts = resample_by_arclength(name, 512)
                height = float(pts[:, 1].max() - pts[:, 1].min())
                self.assertGreater(height, 0.05)
                self.assertLess(height, 20.0)

    def test_no_shape_has_a_zero_length_segment(self):
        for name in SHAPES:
            with self.subTest(shape=name):
                pts = resample_by_arclength(name, 256)
                closed = np.vstack([pts, pts[:1]])
                steps = np.hypot(*np.diff(closed, axis=0).T)
                self.assertGreater(float(steps.min()), 0.0)


class Resampling(unittest.TestCase):
    def test_points_are_evenly_spaced_by_arc_length(self):
        """Not by parameter t. Uniform t piles samples into the cusps."""
        for name in ("heart", "star5", "trex"):
            with self.subTest(shape=name):
                pts = resample_by_arclength(name, 400)
                closed = np.vstack([pts, pts[:1]])
                steps = np.hypot(*np.diff(closed, axis=0).T)
                # Chords, not arcs: a sample interval crossing a sharp corner
                # covers its arc length in a shorter straight line, so a spiky
                # shape scatters a little even when the arc spacing is exact.
                self.assertLess(float(steps.std() / steps.mean()), 0.10)

    def test_the_count_is_what_was_asked_for(self):
        for n in (8, 40, 333):
            self.assertEqual(len(resample_by_arclength("heart", n)), n)

    def test_resampling_is_deterministic(self):
        a = resample_by_arclength("trex", 128)
        b = resample_by_arclength("trex", 128)
        np.testing.assert_array_equal(a, b)


class Registration(unittest.TestCase):
    def test_a_registered_curve_behaves_like_a_built_in(self):
        curve = np.column_stack([np.cos(np.linspace(0, 2 * np.pi, 200, endpoint=False)),
                                 np.sin(np.linspace(0, 2 * np.pi, 200, endpoint=False))])
        name = register("_test_circle", curve)
        try:
            self.assertIn(name, SHAPES)
            pts = resample_by_arclength(name, 256)
            width = float(pts[:, 0].max() - pts[:, 0].min())
            self.assertAlmostEqual(width, 1.0, places=3)
        finally:
            SHAPES.pop(name, None)


class MultiContourMerge(unittest.TestCase):
    """Several closed contours into ONE closed curve - the pen that cannot lift."""

    @staticmethod
    def ring(centre, radius, n=120):
        t = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
        return np.column_stack([np.cos(t), np.sin(t)]) * radius + np.asarray(centre)

    @staticmethod
    def length(curve):
        return float(np.hypot(*np.diff(np.vstack([curve, curve[:1]]), axis=0).T).sum())

    def test_two_rings_become_one_curve(self):
        a, b = self.ring((0.0, 0.0), 1.0), self.ring((4.0, 0.0), 1.0)
        merged, connector_m, edges = mc.merge([a, b])
        self.assertEqual(merged.ndim, 2)
        self.assertEqual(merged.shape[1], 2)
        self.assertTrue(np.isfinite(merged).all())
        self.assertEqual(len(edges), 1)              # two parts, one connector

    def test_the_merged_curve_passes_near_every_input_contour(self):
        """Every part is visited, or the drawing lost a piece."""
        from scipy.spatial import cKDTree
        rings = [self.ring((0.0, 0.0), 1.0), self.ring((4.0, 0.0), 1.0),
                 self.ring((2.0, 3.5), 0.8)]
        tree = cKDTree(mc.merge(rings)[0])
        for i, ring in enumerate(rings):
            with self.subTest(ring=i):
                self.assertLess(float(tree.query(ring)[0].max()), 0.15)

    def test_a_single_contour_needs_no_connector(self):
        one = self.ring((0.0, 0.0), 1.0)
        merged, connector_m, edges = mc.merge([one])
        self.assertEqual(edges, [])
        self.assertEqual(connector_m, 0)
        self.assertAlmostEqual(self.length(merged), self.length(one), delta=0.05)

    def test_the_curve_is_exactly_the_parts_plus_twice_the_connectors(self):
        """Every connector is travelled out and back - that is the construction.

        The identity is what makes the merged curve safe to push through the
        rest of the pipeline: its length is accounted for, so `wander` and the
        distance model are not quietly paying for the joins.
        """
        rings = [self.ring((0.0, 0.0), 1.0), self.ring((3.0, 0.0), 1.0),
                 self.ring((1.5, 3.0), 0.7)]
        merged, connector_m, edges = mc.merge(rings)
        parts = sum(self.length(r) for r in rings)
        self.assertEqual(len(edges), len(rings) - 1)          # a spanning tree
        self.assertAlmostEqual(self.length(merged), parts + 2 * connector_m,
                               delta=0.05)


if __name__ == "__main__":
    unittest.main()
