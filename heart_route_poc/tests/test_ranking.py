"""Which fit is offered, and which is held back for 「換一個」.

This logic has broken twice, both times producing a button that did nothing,
and until it was pulled out of the 218-line search function there was no way to
test it without downloading a city.

  Variant 1 came back byte-identical to variant 0. Two causes at once: two
  centres MIN_SEPARATION_M apart can snap onto the same junctions and fit the
  same route twice, and variant 0 stops early while variant 1 searches all six,
  so the two runs rank different sets.

  `more: 0` hid the button from every rider whose first answer was good -
  which is most of them - because an early stop genuinely does not know how
  many other placements would have worked.
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


def fit(distance, wander=0.0, excursion=0.0, seed=0.0):
    """One candidate fit, with the lat/lon `_build_route_uncached` attaches."""
    t = np.linspace(0.0, 2 * np.pi, 64, endpoint=False)
    xy = np.column_stack([np.cos(t), np.sin(t)]) * 1000.0 + seed
    return {"distance": distance, "wander": wander, "excursion": excursion,
            "route_xy": xy,
            "coordinates": [[25.0 + a / 111_320.0, 121.5 + b / 111_320.0]
                            for a, b in xy]}


class Admissible(unittest.TestCase):
    """Lexicographic, not weighted: meet the conditions first, then rank."""

    def test_fits_inside_both_limits_win_outright(self):
        good = fit(0.20, wander=0.01, excursion=0.01)
        closer_but_wandering = fit(0.05, wander=0.9, excursion=0.9)
        out = app.admissible_fits([closer_but_wandering, good])
        self.assertEqual(out, [good])

    def test_excursion_is_the_first_fallback(self):
        wandering = fit(0.10, wander=0.9, excursion=0.01)
        straying = fit(0.05, wander=0.01, excursion=0.9)
        out = app.admissible_fits([wandering, straying])
        self.assertEqual(out, [wandering])

    def test_wander_is_the_second_fallback(self):
        straying = fit(0.10, wander=0.01, excursion=0.9)
        both_bad = fit(0.05, wander=0.9, excursion=0.9)
        out = app.admissible_fits([straying, both_bad])
        self.assertEqual(out, [straying])

    def test_a_route_that_breaks_every_limit_still_beats_no_route(self):
        bad = fit(0.5, wander=9.0, excursion=9.0)
        self.assertEqual(app.admissible_fits([bad]), [bad])

    def test_nothing_in_nothing_out(self):
        self.assertEqual(app.admissible_fits([]), [])


class Ranking(unittest.TestCase):
    def setUp(self):
        self.key = ("heart", 30.0, "bike", 25.04, 121.54)
        self.saved = dict(app._ROUTE_CACHE)
        app._ROUTE_CACHE.clear()

    def tearDown(self):
        app._ROUTE_CACHE.clear()
        app._ROUTE_CACHE.update(self.saved)

    def rank(self, fits, variant=0):
        return app.rank_fits(fits, *self.key, variant)

    def test_closest_shape_first(self):
        far, near, middle = fit(0.30, seed=1), fit(0.05, seed=2), fit(0.12, seed=3)
        ranked, _ = self.rank([far, near, middle])
        self.assertEqual([f["distance"] for f in ranked], [0.05, 0.12, 0.30])

    def test_every_fit_is_marked(self):
        ranked, _ = self.rank([fit(0.1, seed=1), fit(0.2, seed=2)])
        self.assertEqual(len({f["mark"] for f in ranked}), 2)

    def test_the_same_ride_from_two_centres_counts_once(self):
        """MIN_SEPARATION_M separates CENTRES, not the routes they snap to."""
        a, b = fit(0.10, seed=5), fit(0.11, seed=5)      # same geometry
        ranked, _ = self.rank([a, b])
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["distance"], 0.10)    # the better of the two

    def test_the_mark_is_a_rounding_and_not_a_tolerance(self):
        """Worth knowing before relying on it.

        Six decimals of latitude collapses routes that are identical, which is
        the case it exists for - the same placement fitted twice comes back bit
        for bit. It does NOT collapse two routes that merely run within 11 cm
        of each other, because two values a centimetre apart can still fall on
        opposite sides of a rounding boundary. Nothing depends on that today;
        it would if the mark were ever asked to mean "near enough".
        """
        a, b = fit(0.10, seed=5.0), fit(0.11, seed=5.0)
        self.assertEqual(len(self.rank([a, b])[0]), 1)          # identical

        c, d = fit(0.10, seed=5.0), fit(0.11, seed=5.5)         # 50 cm apart
        self.assertEqual(len(self.rank([c, d])[0]), 2)

    def test_a_genuinely_different_route_is_kept(self):
        a, b = fit(0.10, seed=5), fit(0.11, seed=4000.0)
        self.assertEqual(len(self.rank([a, b])[0]), 2)

    def test_variant_zero_has_seen_nothing(self):
        fits = [fit(0.1, seed=1), fit(0.2, seed=2)]
        ranked, fresh = self.rank(fits, variant=0)
        self.assertEqual(len(fresh), len(ranked))

    def test_variant_one_will_not_return_what_variant_zero_did(self):
        first, second = fit(0.10, seed=1), fit(0.20, seed=2)
        ranked, fresh = self.rank([first, second], variant=0)
        # Stored as the service stores it: the coordinates, not the mark.
        app._ROUTE_CACHE[app._cache_key(*self.key, 0)] = {
            "coordinates": fresh[0]["coordinates"]}

        ranked, fresh = self.rank([fit(0.10, seed=1), fit(0.20, seed=2)], variant=1)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(len(fresh), 1)
        self.assertEqual(fresh[0]["distance"], 0.20)

    def test_running_out_is_reported_as_an_empty_fresh_list(self):
        """The caller turns that into `exhausted`, and stops offering the button."""
        only = fit(0.10, seed=1)
        _, fresh = self.rank([only], variant=0)
        app._ROUTE_CACHE[app._cache_key(*self.key, 0)] = {
            "coordinates": fresh[0]["coordinates"]}
        ranked, fresh = self.rank([fit(0.10, seed=1)], variant=1)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(fresh, [])

    def test_a_cache_entry_with_no_route_in_it_excludes_nothing(self):
        """A row with nothing to identify must not silently hide every route."""
        app._ROUTE_CACHE[app._cache_key(*self.key, 0)] = {"status": "ok"}
        ranked, fresh = self.rank([fit(0.1, seed=1)], variant=1)
        self.assertEqual(len(fresh), 1)


class RouteMark(unittest.TestCase):
    """The route's identity. It goes into the database, so it has to survive a
    restart - which the `hash()` it used to be did not."""

    def test_the_same_route_marks_the_same(self):
        c = fit(0.1, seed=3)["coordinates"]
        self.assertEqual(app.route_mark(c), app.route_mark(list(c)))

    def test_different_routes_mark_differently(self):
        self.assertNotEqual(app.route_mark(fit(0.1, seed=1)["coordinates"]),
                            app.route_mark(fit(0.1, seed=9000)["coordinates"]))

    def test_a_stored_row_can_be_marked_from_what_it_holds(self):
        """The whole point: an old row is recomputed, never trusted, so the 76
        routes already in the database need no migration."""
        stored = {"coordinates": fit(0.1, seed=7)["coordinates"],
                  "mark": "-7762562177673524048"}       # a pre-fix mark
        self.assertNotEqual(app.route_mark(stored["coordinates"]), stored["mark"])
        self.assertEqual(app.route_mark(stored["coordinates"]),
                         app.route_mark(stored["coordinates"]))

    def test_it_is_the_same_in_another_process(self):
        """The regression that mattered: PYTHONHASHSEED is random per process,
        so a mark written to `_routes.db` never matched one computed after a
        restart, and the variant exclusion silently stopped excluding."""
        import subprocess
        here = str(Path(__file__).resolve().parent.parent)
        code = (f"import sys; sys.path.insert(0, {here!r}); "
                f"sys.path.insert(0, {here + '/server'!r});"
                "import app;"
                "print(app.route_mark([[25.0, 121.5], [25.001, 121.501]]))")
        seen = set()
        for _ in range(3):
            out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                 text=True, timeout=300)
            self.assertEqual(out.returncode, 0, out.stderr[-400:])
            seen.add(out.stdout.strip().splitlines()[-1])
        self.assertEqual(len(seen), 1, f"marks differ between processes: {seen}")

    def test_sub_millimetre_noise_is_rounded_away(self):
        c = fit(0.1, seed=3)["coordinates"]
        self.assertEqual(app.route_mark(c),
                         app.route_mark([[a + 1e-12, b + 1e-12] for a, b in c]))


if __name__ == "__main__":
    unittest.main()
