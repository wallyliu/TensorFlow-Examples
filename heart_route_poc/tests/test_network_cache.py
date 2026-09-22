"""The network cache, in both places it lives.

A box already loaded that CONTAINS the one being asked for will do: the
half-size comes from the shape's width, so the sizes asked for are all slightly
different (8460, 9052, 9997, 13453 m) and almost none of them names a file on
disk. Without that rule, a --precompute run downloaded the same city twenty
times and then died on a 509, and a route restored from the store downloaded a
whole network to draw the map behind it.

The rule is sound because the boxes are concentric squares: a larger half-side
around the same centre strictly contains a smaller one.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routeshape import network as rn


class CachedCovering(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.real = rn.CACHE_DIR
        rn.CACHE_DIR = Path(self.dir.name)

    def tearDown(self):
        rn.CACHE_DIR = self.real
        self.dir.cleanup()

    def touch(self, name):
        (rn.CACHE_DIR / name).write_text("")

    def test_nothing_cached_means_nothing_to_reuse(self):
        self.assertIsNone(rn.cached_covering(25.04, 121.54, "bike", 5000.0))

    def test_a_larger_box_covers_a_smaller_request(self):
        self.touch("_bike_25.0400_121.5400_7000m.graphml")
        got = rn.cached_covering(25.04, 121.54, "bike", 5000.0)
        self.assertEqual(got.name, "_bike_25.0400_121.5400_7000m.graphml")

    def test_a_smaller_box_is_not_offered(self):
        self.touch("_bike_25.0400_121.5400_4500m.graphml")
        self.assertIsNone(rn.cached_covering(25.04, 121.54, "bike", 9000.0))

    def test_the_smallest_covering_box_wins(self):
        """Loading a 20 km graph to answer a 5 km request is not free."""
        for size in (6000, 9000, 15000):
            self.touch(f"_bike_25.0400_121.5400_{size}m.graphml")
        got = rn.cached_covering(25.04, 121.54, "bike", 5500.0)
        self.assertEqual(got.name, "_bike_25.0400_121.5400_6000m.graphml")

    def test_an_exactly_sized_box_is_accepted(self):
        self.touch("_bike_25.0400_121.5400_7000m.graphml")
        self.assertIsNotNone(rn.cached_covering(25.04, 121.54, "bike", 7000.0))

    def test_graphml_is_preferred_over_osm_xml(self):
        """It reloads in a fraction of a second; the XML has to be re-parsed."""
        self.touch("_bike_25.0400_121.5400_6000m.osm")
        self.touch("_bike_25.0400_121.5400_9000m.graphml")
        got = rn.cached_covering(25.04, 121.54, "bike", 5000.0)
        self.assertEqual(got.suffix, ".graphml")

    def test_osm_xml_is_used_when_there_is_no_graphml(self):
        self.touch("_bike_25.0400_121.5400_6000m.osm")
        got = rn.cached_covering(25.04, 121.54, "bike", 5000.0)
        self.assertEqual(got.name, "_bike_25.0400_121.5400_6000m.osm")

    def test_another_place_is_never_offered(self):
        self.touch("_bike_24.8000_120.9700_15000m.graphml")
        self.assertIsNone(rn.cached_covering(25.04, 121.54, "bike", 5000.0))

    def test_another_mode_is_never_offered(self):
        """A cyclist may not use a pavement; the filters differ."""
        self.touch("_walk_25.0400_121.5400_15000m.graphml")
        self.assertIsNone(rn.cached_covering(25.04, 121.54, "bike", 5000.0))

    def test_a_file_that_is_not_a_cache_entry_is_ignored(self):
        self.touch("_bike_25.0400_121.5400_notanumberm.graphml")
        self.touch("_bike_25.0400_121.5400_9000m.graphml")
        got = rn.cached_covering(25.04, 121.54, "bike", 5000.0)
        self.assertEqual(got.name, "_bike_25.0400_121.5400_9000m.graphml")


if __name__ == "__main__":
    unittest.main()
