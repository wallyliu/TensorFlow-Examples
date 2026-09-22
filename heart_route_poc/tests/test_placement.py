"""Where in the city to put the shape: the two-stage search.

Stage 1 is a filter, not a ranking of routes. It asks only "is there pavement
along this curve", which is cheap enough to ask of tens of thousands of
placements and says nothing about whether the pavement connects. Stage 2 pays
for the real answer on a shortlist.

The tests here pin the filter's two decisions - what it scores and what it
rejects outright - and the shortlist's one job, which is not handing stage 2 the
same street corner six times.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routeshape.placement import (MAX_GAP_M, build_center_grid,
                                  build_street_index, place_shape,
                                  select_candidates)
from routeshape.search import coarse_scan
from routeshape.shapes.library import resample_by_arclength
from tests.gridfixture import centre_of, grid

SPACING = 100.0


class PlaceShape(unittest.TestCase):
    """Rotate, then scale, then translate - directly in projected metres."""

    def setUp(self):
        # A unit square, width 1.0, centred: the library's convention.
        self.unit = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]])

    def test_width_m_is_the_shape_own_width(self):
        out = place_shape(self.unit, np.zeros(2), 2000.0, 0.0)
        self.assertAlmostEqual(float(out[:, 0].max() - out[:, 0].min()), 2000.0, places=6)

    def test_the_centre_is_where_it_was_put(self):
        out = place_shape(self.unit, np.array([50000.0, -7000.0]), 2000.0, 0.0)
        np.testing.assert_allclose(out.mean(axis=0), [50000.0, -7000.0], atol=1e-6)

    def test_rotation_turns_the_shape(self):
        out = place_shape(np.array([[1.0, 0.0]]), np.zeros(2), 1.0, 90.0)
        np.testing.assert_allclose(out[0], [0.0, 1.0], atol=1e-9)

    def test_width_m_still_means_the_shape_own_width_when_tilted(self):
        """Rotation happens BEFORE scaling, so width_m survives the tilt."""
        turned = place_shape(self.unit, np.zeros(2), 2000.0, 45.0)
        span = float(np.hypot(*(turned[1] - turned[0])))
        self.assertAlmostEqual(span, 2000.0, places=6)


class StreetIndex(unittest.TestCase):
    def test_edges_are_sampled_not_just_nodes(self):
        """Junctions sit 100-200 m apart; a node-only index would report a
        contour running down the middle of a block as 80 m from a street."""
        g = grid(10, SPACING)
        tree = build_street_index(g, spacing=15.0)
        self.assertGreater(tree.n, g.number_of_nodes() * 2)
        # A point halfway along a block is metres from the index, not tens.
        midblock = np.array([[g.nodes[0]["x"] + SPACING / 2, g.nodes[0]["y"]]])
        self.assertLess(float(tree.query(midblock)[0][0]), 15.0)


class CoarseScan(unittest.TestCase):
    def setUp(self):
        self.g = grid(40, SPACING)
        self.tree = build_street_index(self.g, spacing=15.0)
        self.centre = np.array(centre_of(self.g))

    def test_a_placement_on_the_grid_scores_better_than_one_off_its_edge(self):
        inside = self.centre[None, :]
        outside = (self.centre + np.array([6000.0, 6000.0]))[None, :]
        here = coarse_scan(self.tree, inside, "triangle", 1500.0, (0.0,))
        there = coarse_scan(self.tree, outside, "triangle", 1500.0, (0.0,))
        self.assertLess(here["score"][0], there["score"][0])

    def test_a_contour_over_open_ground_is_rejected_outright(self):
        """No routing can invent pavement that is not there."""
        far = (self.centre + np.array([40000.0, 0.0]))[None, :]
        scored = coarse_scan(self.tree, far, "triangle", 1500.0, (0.0,))
        self.assertFalse(np.isfinite(scored["score"][0]))
        self.assertGreater(scored["worst"][0] if scored["worst"][0] else MAX_GAP_M + 1,
                           0.0)

    def test_one_row_per_centre_and_rotation(self):
        centres = build_center_grid(self.centre, 800.0, 200.0)[0]
        rotations = (0.0, 30.0, 60.0)
        scored = coarse_scan(self.tree, centres, "triangle", 1000.0, rotations)
        self.assertEqual(len(scored), len(centres) * len(rotations))

    def test_the_score_is_mean_plus_half_the_p95(self):
        """Pinned against the scan's own reported terms, not a stored number."""
        centres = build_center_grid(self.centre, 600.0, 200.0)[0]
        scored = coarse_scan(self.tree, centres, "triangle", 1000.0, (0.0, 90.0))
        finite = scored[np.isfinite(scored["score"])]
        self.assertGreater(len(finite), 0)
        np.testing.assert_allclose(finite["score"],
                                   finite["mean"] + 0.5 * finite["p95"], rtol=1e-9)

    def test_the_p95_term_separates_uniform_error_from_one_bad_stretch(self):
        """Why that term is there.

        A placement uniformly 30 m off is fine - the matcher absorbs it. One
        that is perfect for most of the loop and 200 m off along a riverbank is
        not. At the SAME mean, the score has to charge the second one more.
        """
        uniform = np.full(180, 30.0)
        spiky = np.concatenate([np.full(170, 20.0), np.full(10, 200.0)])
        score = lambda d: d.mean() + 0.5 * np.percentile(d, 95)
        self.assertAlmostEqual(float(uniform.mean()), float(spiky.mean()), delta=0.1)
        self.assertGreater(score(spiky), score(uniform) * 1.5)


class Shortlist(unittest.TestCase):
    """Greedy non-maximum suppression: the best placement in each AREA."""

    @staticmethod
    def rows(points):
        return np.array([(x, y, 0.0, s, 0.0, 0.0, 0.0) for x, y, s in points],
                        dtype=[("x", float), ("y", float), ("rotation", float),
                               ("score", float), ("mean", float), ("p95", float),
                               ("worst", float)])

    def test_near_duplicates_are_suppressed(self):
        scored = self.rows([(0.0, 0.0, 1.0), (50.0, 0.0, 1.1), (100.0, 0.0, 1.2),
                            (5000.0, 0.0, 2.0)])
        chosen = select_candidates(scored, n=4, min_separation_m=700.0)
        self.assertEqual(len(chosen), 2)
        self.assertAlmostEqual(float(chosen[0]["x"]), 0.0)
        self.assertAlmostEqual(float(chosen[1]["x"]), 5000.0)

    def test_the_best_in_each_area_is_the_one_kept(self):
        scored = self.rows([(0.0, 0.0, 9.0), (100.0, 0.0, 1.0)])
        chosen = select_candidates(scored, n=2, min_separation_m=700.0)
        self.assertEqual(len(chosen), 1)
        self.assertAlmostEqual(float(chosen[0]["score"]), 1.0)

    def test_rejected_placements_are_never_shortlisted(self):
        scored = self.rows([(0.0, 0.0, np.inf), (5000.0, 0.0, 2.0)])
        chosen = select_candidates(scored, n=4, min_separation_m=700.0)
        self.assertEqual(len(chosen), 1)
        self.assertAlmostEqual(float(chosen[0]["x"]), 5000.0)

    def test_never_returns_more_than_asked(self):
        scored = self.rows([(i * 2000.0, 0.0, float(i)) for i in range(20)])
        self.assertEqual(len(select_candidates(scored, n=6, min_separation_m=700.0)), 6)


class CenterGrid(unittest.TestCase):
    def test_centres_stay_inside_the_margin(self):
        region = np.array([1000.0, 2000.0])
        centres, _, _ = build_center_grid(region, 800.0, 200.0)
        self.assertTrue((np.abs(centres - region) <= 800.0 + 1e-9).all())
        self.assertGreater(len(centres), 1)


if __name__ == "__main__":
    unittest.main()
