"""The Viterbi map matcher, on a grid whose right answer is known.

This is the part BACKLOG 54 proposes to rewrite - networkx Dijkstra out,
scipy.sparse.csgraph in - so it is the part that most needs an oracle. On a
regular grid the shortest path between two junctions is any staircase between
them and its length is exactly the Manhattan distance, so these tests assert
arithmetic rather than "whatever it returned last time".

The end-to-end case is the load-bearing one: a square whose corners land on
grid nodes has a perfect answer, and the matcher finds it. Detour 1.0003,
nothing backtracked, shape distance 0.0. Any rewrite that does not reproduce
those three numbers has changed what the matcher chooses.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routeshape.matching import (NoRouteFoundError, build_candidate_sets,
                                 compute_transition_costs, route_to_xy,
                                 fit_route, viterbi_closed_loop)
from routeshape.metrics import shape_distance
from tests.gridfixture import centre_of, circle, grid, square

SPACING = 100.0


class CandidateSets(unittest.TestCase):
    """Improvement 2: keep k nearest junctions per point, commit to none."""

    def setUp(self):
        self.g = grid(24, SPACING)
        self.target = square(1200.0, (1200.0, 1200.0), 40)

    def test_keeps_k_per_point(self):
        cand, _ = build_candidate_sets(self.g, self.target, k=6, radius_m=400.0)
        self.assertEqual(len(cand), len(self.target))
        for row in cand:
            self.assertEqual(len(row), 6)

    def test_excludes_nodes_that_are_not_junctions(self):
        """A dead end can only be left the way it was entered (POC 1).

        `min_degree=3` on the undirected view, so a grid's four corners (degree
        2) and its edge midpoints (degree 3) sort themselves out: corners are
        never offered.
        """
        cand, _ = build_candidate_sets(self.g, self.target, k=10, radius_m=2000.0)
        undirected = self.g.to_undirected()
        for row in cand:
            for node in row:
                self.assertGreaterEqual(undirected.degree(node), 3)

    def test_radius_is_respected_but_never_leaves_a_point_stranded(self):
        # A radius far tighter than the grid spacing: every point must still
        # get exactly its single nearest junction rather than an empty set.
        cand, emis = build_candidate_sets(self.g, self.target, k=10, radius_m=1.0)
        for row in cand:
            self.assertEqual(len(row), 1)
        self.assertEqual(len(emis), len(self.target))

    def test_emission_is_the_snap_distance(self):
        cand, emis = build_candidate_sets(self.g, self.target, k=4, radius_m=400.0)
        for point, row, costs in zip(self.target, cand, emis):
            for node in row:
                here = np.array([self.g.nodes[node]["x"], self.g.nodes[node]["y"]])
                self.assertAlmostEqual(costs[node], float(np.hypot(*(here - point))),
                                       places=6)

    def test_a_per_point_radius_is_accepted(self):
        """Freedom is the lever, not price - so the radius has to vary per point."""
        radii = [60.0] * 20 + [500.0] * 20
        cand, _ = build_candidate_sets(self.g, self.target, k=10, radius_m=radii)
        tight = sum(len(r) for r in cand[:20])
        loose = sum(len(r) for r in cand[20:])
        self.assertLess(tight, loose)

    def test_a_wrong_length_radius_is_refused(self):
        with self.assertRaises(ValueError):
            build_candidate_sets(self.g, self.target, k=4, radius_m=[100.0, 200.0])


class TransitionCosts(unittest.TestCase):
    """excess detour + deviation_weight x mean distance from the ideal curve."""

    def setUp(self):
        self.g = grid(24, SPACING)
        self.target = square(1200.0, (1200.0, 1200.0), 24)
        self.cand, _ = build_candidate_sets(self.g, self.target, k=4, radius_m=400.0)

    def test_one_step_per_point_and_it_wraps(self):
        steps = compute_transition_costs(self.g, self.cand, self.target)
        self.assertEqual(len(steps), len(self.target))
        # The last step joins the last point back to the FIRST - the loop closes.
        last = steps[-1]
        self.assertTrue(last)
        for u, v in last:
            self.assertIn(u, self.cand[-1])
            self.assertIn(v, self.cand[0])

    def test_costs_are_never_negative(self):
        steps = compute_transition_costs(self.g, self.cand, self.target)
        for step in steps:
            for cost in step.values():
                self.assertGreaterEqual(cost, 0.0)

    def test_excess_detour_is_manhattan_minus_the_straight_line(self):
        """With the deviation term off, the cost is arithmetic on a grid."""
        steps = compute_transition_costs(self.g, self.cand, self.target,
                                         reference_tree=None, deviation_weight=0.0)
        for i, step in enumerate(steps):
            j = (i + 1) % len(self.target)
            gap = float(np.hypot(*(self.target[j] - self.target[i])))
            for (u, v), cost in step.items():
                pu = np.array([self.g.nodes[u]["x"], self.g.nodes[u]["y"]])
                pv = np.array([self.g.nodes[v]["x"], self.g.nodes[v]["y"]])
                manhattan = float(abs(pu[0] - pv[0]) + abs(pu[1] - pv[1]))
                self.assertAlmostEqual(cost, max(0.0, manhattan - gap), places=6)

    def test_the_deviation_term_only_ever_adds(self):
        from scipy.spatial import cKDTree
        from routeshape.matching import _densify
        ref = cKDTree(_densify(square(1200.0, (1200.0, 1200.0), 4000), spacing=5.0))
        bare = compute_transition_costs(self.g, self.cand, self.target,
                                        reference_tree=None, deviation_weight=0.0)
        with_dev = compute_transition_costs(self.g, self.cand, self.target,
                                            reference_tree=ref, deviation_weight=10.0)
        for a, b in zip(bare, with_dev):
            for pair, cost in a.items():
                self.assertGreaterEqual(b[pair], cost - 1e-9)


class Viterbi(unittest.TestCase):
    """Improvement 3: one candidate per point, chosen over the whole closed loop."""

    def setUp(self):
        self.g = grid(24, SPACING)
        self.target = square(1200.0, (1200.0, 1200.0), 24)
        self.cand, self.emis = build_candidate_sets(self.g, self.target, k=4,
                                                    radius_m=400.0)
        self.steps = compute_transition_costs(self.g, self.cand, self.target,
                                              reference_tree=None,
                                              deviation_weight=0.0)

    def test_picks_one_candidate_per_point_from_its_own_set(self):
        chosen, _ = viterbi_closed_loop(self.cand, self.emis, self.steps)
        self.assertEqual(len(chosen), len(self.target))
        for node, row in zip(chosen, self.cand):
            self.assertIn(node, row)

    def test_the_reported_cost_is_the_assignment_it_returned(self):
        chosen, cost = viterbi_closed_loop(self.cand, self.emis, self.steps,
                                           snap_weight=1.0)
        recomputed = sum(self.emis[i][n] for i, n in enumerate(chosen))
        recomputed += sum(self.steps[i][(chosen[i], chosen[(i + 1) % len(chosen)])]
                          for i in range(len(chosen)))
        self.assertAlmostEqual(cost, recomputed, places=6)

    def test_it_beats_snapping_each_point_to_its_nearest_junction(self):
        """The trade POC 1 could not make, stated as a test.

        Nearest-node is the cheapest possible emission cost and it is what the
        DP must be allowed to reject - a junction 60 m off a through street
        beats one 20 m off that needs a 300 m detour.
        """
        chosen, cost = viterbi_closed_loop(self.cand, self.emis, self.steps)
        greedy = [min(row, key=lambda n: self.emis[i][n])
                  for i, row in enumerate(self.cand)]
        greedy_cost = sum(self.emis[i][n] for i, n in enumerate(greedy))
        for i in range(len(greedy)):
            pair = (greedy[i], greedy[(i + 1) % len(greedy)])
            greedy_cost += self.steps[i].get(pair, float("inf"))
        self.assertLessEqual(cost, greedy_cost + 1e-9)

    def test_snap_weight_may_be_per_point(self):
        chosen, _ = viterbi_closed_loop(self.cand, self.emis, self.steps,
                                        snap_weight=[1.0] * len(self.target))
        self.assertEqual(len(chosen), len(self.target))

    def test_a_wrong_length_snap_weight_is_refused(self):
        with self.assertRaises(ValueError):
            viterbi_closed_loop(self.cand, self.emis, self.steps,
                                snap_weight=[1.0, 2.0])

    def test_raising_the_snap_weight_pulls_the_route_onto_the_contour(self):
        loose, _ = viterbi_closed_loop(self.cand, self.emis, self.steps,
                                       snap_weight=0.0)
        tight, _ = viterbi_closed_loop(self.cand, self.emis, self.steps,
                                       snap_weight=1000.0)
        snap = lambda a: sum(self.emis[i][n] for i, n in enumerate(a))
        self.assertLessEqual(snap(tight), snap(loose) + 1e-9)

    def test_an_unreachable_loop_is_reported_not_guessed(self):
        empty = [dict() for _ in self.steps]
        with self.assertRaises(NoRouteFoundError):
            viterbi_closed_loop(self.cand, self.emis, empty)


class EndToEnd(unittest.TestCase):
    """The oracle. A square on grid nodes has a perfect answer; find it."""

    def test_a_grid_aligned_square_is_fitted_exactly(self):
        g = grid(24, SPACING)
        target = square(1200.0, (1200.0, 1200.0), 40)
        reference = square(1200.0, (1200.0, 1200.0), 4000)
        out = fit_route(g, target, reference, k=6, snap_weight=1.0,
                       radius_m=260.0, deviation_weight=10.0)
        m = out["metrics"]

        self.assertAlmostEqual(m["route_km"], 4.8, places=2)   # 4 x 1200 m
        self.assertAlmostEqual(m["detour_ratio"], 1.0, delta=0.01)
        self.assertEqual(m["backtracked_edges"], 0)
        self.assertEqual(m["failed_segments"], 0)
        self.assertLess(shape_distance(out["route_xy"], reference), 1e-6)

    def test_a_circle_is_fitted_recognisably_but_not_exactly(self):
        """The control. No grid can draw a circle, so it must cost something."""
        g = grid(24, SPACING)
        centre = centre_of(g)
        target = circle(600.0, centre, 40)
        reference = circle(600.0, centre, 4000)
        out = fit_route(g, target, reference, k=6, snap_weight=1.0,
                       radius_m=260.0, deviation_weight=10.0)
        distance = shape_distance(out["route_xy"], reference)
        self.assertGreater(distance, 0.0)
        self.assertLess(distance, 0.10)            # inside the perceptual threshold
        self.assertGreater(out["metrics"]["detour_ratio"], 1.0)

    def test_a_barrier_with_no_crossing_is_reported_not_routed_around(self):
        """A river the network cannot cross is a real outcome, not a bug."""
        n = 24
        wall = frozenset((12, j) for j in range(n))      # a full-height column
        g = grid(n, SPACING, missing=wall)
        # Straddle the wall deliberately.
        target = square(1200.0, (1200.0, 1200.0), 40)
        reference = square(1200.0, (1200.0, 1200.0), 4000)
        with self.assertRaises(NoRouteFoundError):
            fit_route(g, target, reference, k=6, snap_weight=1.0,
                     radius_m=260.0, deviation_weight=10.0)


class RouteGeometry(unittest.TestCase):
    def test_route_to_xy_follows_the_edges(self):
        g = grid(6, SPACING)
        path = [0, 1, 2, 8, 14]
        xy = route_to_xy(g, path)
        self.assertGreaterEqual(len(xy), len(path))
        np.testing.assert_allclose(xy[0], [g.nodes[0]["x"], g.nodes[0]["y"]])
        np.testing.assert_allclose(xy[-1], [g.nodes[14]["x"], g.nodes[14]["y"]])


if __name__ == "__main__":
    unittest.main()
