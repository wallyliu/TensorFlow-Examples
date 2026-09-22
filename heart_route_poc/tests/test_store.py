"""The route store: what survives a restart, and what must not.

The fingerprint is the part these tests exist for. The gear got its centre bore
between two rounds of this project and the house got a door; "gear" was two
different pictures pooled under one name, which corrupted the rater pool for
weeks before anyone noticed (BACKLOG 45). A stored route carries a hash of the
outline it was fitted to, and a row whose shape no longer hashes the same is
dropped at load rather than served.

That is a silent-corruption bug, which is the kind no amount of looking at the
page catches. It gets a test.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "server"))

import store                                             # noqa: E402
from routeshape.shapes.library import SHAPES, register   # noqa: E402


def an_answer(shape="heart", km=30.0, streets=True):
    answer = {"shape": shape, "status": "ok", "route_km": km,
              "coordinates": [[25.04, 121.54], [25.05, 121.55], [25.04, 121.56]],
              "_lat": 25.04, "_lon": 121.54, "id": "abc123"}
    if streets:
        answer["streets"] = [[[25.04, 121.54], [25.05, 121.55]]] * 500
    return answer


def a_key(shape="heart", km=30.0, variant=0):
    return (shape, km, "bike", 25.04, 121.54, variant)


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = store.Store(Path(self.dir.name) / "t.db")

    def tearDown(self):
        self.dir.cleanup()

    def test_what_went_in_comes_back_under_the_same_key(self):
        self.db.put(a_key(), an_answer())
        restored, dropped = self.db.load()
        self.assertEqual(dropped, 0)
        self.assertIn(a_key(), restored)
        self.assertEqual(restored[a_key()]["route_km"], 30.0)

    def test_the_street_background_is_not_stored(self):
        """1,045 KB of a 1,068 KB answer. Regenerated on the way out."""
        self.db.put(a_key(), an_answer(streets=True))
        restored, _ = self.db.load()
        self.assertNotIn("streets", restored[a_key()])
        self.assertIn("coordinates", restored[a_key()])

    def test_variants_are_separate_rows(self):
        self.db.put(a_key(variant=0), an_answer())
        self.db.put(a_key(variant=1), an_answer())
        restored, _ = self.db.load()
        self.assertEqual(len(restored), 2)

    def test_writing_the_same_key_twice_replaces_it(self):
        self.db.put(a_key(), an_answer(km=30.0))
        self.db.put(a_key(), an_answer(km=31.0))
        restored, _ = self.db.load()
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[a_key()]["route_km"], 31.0)
        self.assertEqual(self.db.count(), 1)

    def test_a_shape_that_is_not_in_the_library_is_not_stored(self):
        self.db.put(a_key(shape="_not_a_shape"), an_answer(shape="_not_a_shape"))
        self.assertEqual(self.db.count(), 0)


class Invalidation(unittest.TestCase):
    """A stored route is only valid while the shape still means what it meant."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = store.Store(Path(self.dir.name) / "t.db")
        t = np.linspace(0.0, 2 * np.pi, 200, endpoint=False)
        self.circle = np.column_stack([np.cos(t), np.sin(t)])
        register("_test_redrawn", self.circle)

    def tearDown(self):
        SHAPES.pop("_test_redrawn", None)
        self.dir.cleanup()

    def test_a_redrawn_shape_drops_its_rows(self):
        key = a_key(shape="_test_redrawn")
        self.db.put(key, an_answer(shape="_test_redrawn"))
        self.assertEqual(len(self.db.load()[0]), 1)

        # Redraw it - a squashed circle, same name. This is the gear's bore.
        register("_test_redrawn", self.circle * np.array([1.0, 0.4]))
        restored, dropped = self.db.load()
        self.assertEqual(restored, {})
        self.assertEqual(dropped, 1)
        self.assertEqual(self.db.count(), 0)        # and deleted, not just hidden

    def test_the_same_drawing_keeps_its_rows(self):
        key = a_key(shape="_test_redrawn")
        self.db.put(key, an_answer(shape="_test_redrawn"))
        register("_test_redrawn", self.circle.copy())     # identical, re-registered
        restored, dropped = self.db.load()
        self.assertEqual(dropped, 0)
        self.assertIn(key, restored)

    def test_a_withdrawn_shape_drops_its_rows(self):
        key = a_key(shape="_test_redrawn")
        self.db.put(key, an_answer(shape="_test_redrawn"))
        SHAPES.pop("_test_redrawn")
        restored, dropped = self.db.load()
        self.assertEqual(restored, {})
        self.assertEqual(dropped, 1)

    def test_rows_written_before_variants_existed_are_dropped(self):
        """A five-part key cannot be read as a six-part one; do not guess."""
        self.db.put(a_key(shape="_test_redrawn"), an_answer(shape="_test_redrawn"))
        with store._lock:
            self.db._db.execute("UPDATE routes SET key = ?",
                                ("_test_redrawn|30.0|bike|25.04|121.54",))
            self.db._db.commit()
        restored, dropped = self.db.load()
        self.assertEqual(restored, {})
        self.assertEqual(dropped, 1)


class Fingerprint(unittest.TestCase):
    def test_it_follows_the_outline_not_the_name(self):
        t = np.linspace(0.0, 2 * np.pi, 200, endpoint=False)
        circle = np.column_stack([np.cos(t), np.sin(t)])
        register("_fp_a", circle)
        register("_fp_b", circle.copy())
        register("_fp_c", circle * np.array([1.0, 0.4]))
        try:
            self.assertEqual(store.fingerprint("_fp_a"), store.fingerprint("_fp_b"))
            self.assertNotEqual(store.fingerprint("_fp_a"), store.fingerprint("_fp_c"))
        finally:
            for name in ("_fp_a", "_fp_b", "_fp_c"):
                SHAPES.pop(name, None)

    def test_it_is_stable_across_calls(self):
        self.assertEqual(store.fingerprint("heart"), store.fingerprint("heart"))


class Persistence(unittest.TestCase):
    def test_a_new_process_reads_what_the_old_one_wrote(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.db"
            store.Store(path).put(a_key(), an_answer())
            restored, dropped = store.Store(path).load()     # a fresh connection
            self.assertEqual(dropped, 0)
            self.assertIn(a_key(), restored)


if __name__ == "__main__":
    unittest.main()
