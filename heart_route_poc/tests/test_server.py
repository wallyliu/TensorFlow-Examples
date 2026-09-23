"""The service layer's own decisions, with no map and no HTTP.

Everything here is a pure function of a request or of an answer: what the cache
key is, how big a network a restored route needs behind it, whether a shape may
be tilted, what the planner refuses. They are small, and every one of them has
been wrong at least once in a way that reached the page.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "server"))

import app                                               # noqa: E402


class CacheKey(unittest.TestCase):
    def test_the_same_request_written_differently_is_one_key(self):
        """Otherwise a rider who nudges the slider pays for a route twice."""
        self.assertEqual(app._cache_key("heart", 30, "bike", 25.04, 121.54),
                         app._cache_key("heart", 30.0, "bike", 25.040001, 121.540004))

    def test_distance_is_kept_to_a_tenth_of_a_km(self):
        self.assertEqual(app._cache_key("heart", 30.04, "bike", 25.04, 121.54),
                         app._cache_key("heart", 30.0, "bike", 25.04, 121.54))
        self.assertNotEqual(app._cache_key("heart", 30.5, "bike", 25.04, 121.54),
                            app._cache_key("heart", 30.0, "bike", 25.04, 121.54))

    def test_variant_is_part_of_the_key(self):
        self.assertNotEqual(app._cache_key("heart", 30.0, "bike", 25.04, 121.54, 0),
                            app._cache_key("heart", 30.0, "bike", 25.04, 121.54, 1))

    def test_mode_is_part_of_the_key(self):
        self.assertNotEqual(app._cache_key("heart", 30.0, "bike", 25.04, 121.54),
                            app._cache_key("heart", 30.0, "walk", 25.04, 121.54))

    def test_variant_defaults_to_zero(self):
        self.assertEqual(app._cache_key("heart", 30.0, "bike", 25.04, 121.54)[5], 0)


class StreetBackgroundBox(unittest.TestCase):
    """How big a network a route restored from the store needs behind it.

    Asked for the default 4,500 m box whatever its length, 43 of the 76 stored
    routes came back with the map ending part-way along the line - every 50 km
    and 100 km one. It never showed in a single process, because the fit had
    already loaded a box the shape's width.
    """

    @staticmethod
    def route(reach_m):
        """A square loop reaching `reach_m` from 25.04, 121.54."""
        d = reach_m / 111_320.0
        lat, lon = 25.04, 121.54
        ring = [[lat - d, lon - d], [lat - d, lon + d],
                [lat + d, lon + d], [lat + d, lon - d]]
        return {"_lat": lat, "_lon": lon, "coordinates": ring}

    def test_a_short_route_gets_the_default_box(self):
        self.assertEqual(app._street_half_size_m(self.route(500.0)),
                         app.NETWORK_HALF_SIZE_M)

    def test_a_long_route_gets_a_box_that_covers_it(self):
        for reach in (7000.0, 13000.0):
            with self.subTest(reach=reach):
                half = app._street_half_size_m(self.route(reach))
                self.assertGreater(half, reach)
                self.assertGreater(half, app.NETWORK_HALF_SIZE_M)

    def test_the_box_leaves_room_for_the_map_to_keep_drawing(self):
        """`streets_near` pads by STREET_PAD_M past the route."""
        half = app._street_half_size_m(self.route(7000.0))
        self.assertGreaterEqual(half, 7000.0 + app.STREET_PAD_M - 50.0)

    def test_sizes_are_quantised_so_one_box_serves_many_routes(self):
        """Asked for its exact reach, each route named a size of its own: 48
        distinct half-sizes for 79 stored routes. The reuse rule then almost
        never found a loaded box close above the request."""
        # The pad is added BEFORE rounding, so 6,000 m serves every route
        # reaching 4,600 to 5,600 m.
        for reach in (4700.0, 5000.0, 5400.0, 5599.0):
            with self.subTest(reach=reach):
                self.assertEqual(app._street_half_size_m(self.route(reach)), 6000.0)
        self.assertEqual(app._street_half_size_m(self.route(5700.0)), 7000.0)

    def test_every_size_is_the_floor_or_a_whole_step(self):
        for reach in (100.0, 3000.0, 4100.0, 4200.0, 7700.0, 13000.0):
            with self.subTest(reach=reach):
                half = app._street_half_size_m(self.route(reach))
                self.assertTrue(half == app.NETWORK_HALF_SIZE_M
                                or half % app.BOX_STEP_M == 0, half)

    def test_quantising_never_shrinks_the_box_below_the_route(self):
        """Rounding UP, always - a box that does not contain the route is a map
        with a hole in it, which is the bug BACKLOG 55 was about."""
        for reach in (4600.0, 5001.0, 6999.0, 9500.0, 13400.0):
            with self.subTest(reach=reach):
                half = app._street_half_size_m(self.route(reach))
                self.assertGreaterEqual(half, reach + app.STREET_PAD_M)

    def test_it_grows_with_the_route(self):
        sizes = [app._street_half_size_m(self.route(r))
                 for r in (1000.0, 6000.0, 9000.0, 13000.0)]
        self.assertEqual(sizes, sorted(sizes))

    def test_an_answer_with_nothing_to_measure_falls_back(self):
        for answer in ({}, {"coordinates": []},
                       {"coordinates": [[25.0, 121.0]]},      # no centre
                       {"_lat": 25.0, "_lon": 121.0, "coordinates": []}):
            with self.subTest(answer=answer):
                self.assertEqual(app._street_half_size_m(answer),
                                 app.NETWORK_HALF_SIZE_M)


class Rotation(unittest.TestCase):
    def test_a_word_is_pinned_upright(self):
        """POC 12: with rotation free the search returns tilted words, the
        metric scores them BETTER, and nobody can read them."""
        name = app.text_shape("LOVE")
        try:
            self.assertEqual(app.rotations_for(name), (0.0,))
            self.assertTrue(app.is_text(name))
        finally:
            app.SHAPES.pop(name, None)

    def test_everything_else_keeps_the_full_sweep(self):
        self.assertEqual(app.rotations_for("heart"), app.ROTATIONS_DEG)
        self.assertGreater(len(app.rotations_for("heart")), 1)
        self.assertFalse(app.is_text("heart"))


class Thumbnails(unittest.TestCase):
    def test_the_outline_is_the_shape_normalised_for_a_card(self):
        """Centred on the MEAN and divided by the longer span, so the thumbnail
        keeps the shape's proportions and fits a fixed box either way up."""
        for name in ("heart", "trex", "star5"):
            with self.subTest(shape=name):
                outline = app.outline_for(name, points=48)
                self.assertEqual(len(outline), 48)
                xy = np.asarray(outline, dtype=float)
                span = xy.max(axis=0) - xy.min(axis=0)
                self.assertAlmostEqual(float(span.max()), 1.0, delta=0.05)
                self.assertLess(float(np.abs(xy).max()), 1.0)

    def test_it_is_cached_and_identical(self):
        self.assertEqual(app.outline_for("heart"), app.outline_for("heart"))


class Planning(unittest.TestCase):
    def test_a_distance_below_the_floor_is_refused_with_the_number(self):
        answer = app.plan("trex", 1.0, "bike")
        self.assertFalse(answer["feasible"])
        self.assertGreater(answer["min_km"], 1.0)
        self.assertIn("km", answer["message"])

    def test_a_shape_too_wide_to_place_is_refused_here_not_after_stitching(self):
        """Answering 'feasible' and then spending 19 seconds to say 'no
        placement' is a worse answer than no, for having taken longer."""
        answer = app.plan("heart", 100000.0, "bike")
        self.assertFalse(answer["feasible"])
        self.assertIn("tops out", answer["message"])

    def test_a_workable_request_carries_what_the_search_needs(self):
        answer = app.plan("heart", 30.0, "bike")
        self.assertTrue(answer["feasible"])
        self.assertGreater(answer["width_m"], 0)
        self.assertGreaterEqual(answer["points"], answer["n_min"])

    def test_the_label_is_human_readable(self):
        self.assertEqual(app.plan("heart", 30.0, "bike")["label"], "愛心")


class Library(unittest.TestCase):
    def test_every_offered_shape_is_drawable_and_rateable(self):
        for name in app.SHAPES:
            with self.subTest(shape=name):
                self.assertIn(name, app.LABELS)
                self.assertGreaterEqual(app.rf.n_min(name), 4)
                self.assertIsInstance(app.quality_for(name), tuple)

    def test_withdrawn_subjects_are_not_offered(self):
        """Shapes nobody could name were retired; they must not come back."""
        for name in app.shape_pack.WITHDRAWN_SUBJECTS:
            with self.subTest(shape=name):
                self.assertNotIn("e_" + name, app.SHAPES)


class Describe(unittest.TestCase):
    """Typed description to shape. The back end is stubbed: what is under test
    is what this service does with a proposal, not what a model proposes.

    The success path had never run. Without credentials `propose` raises, the
    service reports "unavailable", and the page falls back to the library - so
    a NameError three lines further on sat there through every manual test of
    the feature.
    """

    def setUp(self):
        self.real = app.describe_shape.propose
        t = np.linspace(0.0, 2 * np.pi, 120, endpoint=False)
        self.points = np.column_stack([np.cos(t), np.sin(t) * 0.8])

    def tearDown(self):
        app.describe_shape.propose = self.real
        for name in [n for n in app.SHAPES if n.startswith("gen_")]:
            app.SHAPES.pop(name, None)
            app.LABELS.pop(name, None)

    def stub(self, **over):
        answer = {"status": "ok", "name": "Cat Face", "label": "貓",
                  "points": self.points.tolist()}
        answer.update(over)
        app.describe_shape.propose = lambda *a, **k: answer

    def test_an_accepted_proposal_becomes_a_shape_the_search_can_draw(self):
        self.stub()
        out = app.describe({"description": "a cat"})
        self.assertEqual(out["status"], "ok")
        self.assertIn(out["shape"], app.SHAPES)
        self.assertGreater(out["min_km"], 0.0)
        self.assertFalse(out["recognition_measured"])

    def test_the_generated_name_is_safe_to_use_as_a_key(self):
        self.stub(name="Cat Face!! <script>")
        name = app.describe({"description": "a cat"})["shape"]
        self.assertTrue(name.startswith("gen_"))
        self.assertTrue(all(c.islower() or c.isdigit() or c == "_" for c in name))

    def test_a_rejected_proposal_is_passed_through_untouched(self):
        self.stub(status="rejected", reason="self-intersecting")
        out = app.describe({"description": "a cat"})
        self.assertEqual(out["status"], "rejected")
        self.assertNotIn("shape", out)

    def test_no_credentials_is_a_state_not_a_crash(self):
        def raises(*a, **k):
            raise RuntimeError("no token")
        app.describe_shape.propose = raises
        out = app.describe({"description": "a cat"})
        self.assertEqual(out["status"], "unavailable")

    def test_an_empty_or_oversized_description_is_refused_before_the_model(self):
        for text in ("", "   ", "x" * 201):
            with self.subTest(text=text[:12]):
                self.assertEqual(app.describe({"description": text})["status"], "error")


class NetworkReuse(unittest.TestCase):
    """Which loaded box answers a request, and why the smallest one has to.

    `streets_near` walks every edge of whatever network it is handed, so being
    served a 13,453 m box for a route that reaches 3.6 km costs 4.89 s against
    2.31 s and returns the same 36,500 polylines. The rule is: the smallest
    LOADED box that contains the request.
    """

    def setUp(self):
        self.saved = dict(app._networks)
        app._networks.clear()

    def tearDown(self):
        app._networks.clear()
        app._networks.update(self.saved)

    def fake(self, half):
        app._networks[(25.04, 121.54, "bike", round(half))] = {"half": half}

    def test_the_smallest_box_that_contains_the_request_wins(self):
        self.fake(4500)
        self.fake(13453)
        self.assertEqual(app.network(25.04, 121.54, "bike", 4000.0)["half"], 4500)
        self.assertEqual(app.network(25.04, 121.54, "bike", 4500.0)["half"], 4500)
        self.assertEqual(app.network(25.04, 121.54, "bike", 9000.0)["half"], 13453)

    def test_a_box_too_small_is_never_offered(self):
        """It would hand back a map with a hole in it. Better to load one."""
        self.fake(4500)
        # Nothing loaded covers 9 km, so this would go and build one - which is
        # what we assert by refusing to let it, rather than downloading here.
        key = (25.04, 121.54, "bike", 4500)
        bigger = [k for k in app._networks if k[:3] == key[:3] and k[3] >= 9000]
        self.assertEqual(bigger, [])

    def test_another_place_is_never_reused(self):
        self.fake(13453)
        other = [k for k in app._networks
                 if k[:3] == (24.80, 120.97, "bike") and k[3] >= 4000]
        self.assertEqual(other, [])


if __name__ == "__main__":
    unittest.main()
