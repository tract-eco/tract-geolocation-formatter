"""
Unit tests for the GH-7 self-intersection coordinate helpers.

Tests the pure-Shapely module-level helpers in TRACT_Geolocation_Formatter:
- _find_self_intersection_points_in_shape
- _dedupe_points
- _format_self_intersection_message

Requires Shapely; the import of the module under test additionally requires
qgis.PyQt to be importable (because the module imports it at the top). Tests
skip gracefully if either is missing — same pattern as test_build_expression_value.py.
"""

import unittest

try:
    from shapely.geometry import Polygon, MultiPolygon
    from tract_geolocation_formatter.TRACT_Geolocation_Formatter import (
        _find_self_intersection_points_in_shape,
        _dedupe_points,
        _format_self_intersection_message,
    )

    HELPERS_AVAILABLE = True
except ImportError:
    HELPERS_AVAILABLE = False


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires Shapely + qgis.PyQt to import")
class TestFindSelfIntersectionPointsInShape(unittest.TestCase):
    """Finder-level tests — exercise the segment-pair iteration on Shapely shapes."""

    def test_single_intersection_polygon(self):
        """AC-1: classic bow-tie polygon crosses itself at exactly (0.5, 0.5)."""
        bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
        points = _find_self_intersection_points_in_shape(bowtie)
        self.assertEqual(len(points), 1)
        x, y = points[0]
        self.assertAlmostEqual(x, 0.5, places=9)
        self.assertAlmostEqual(y, 0.5, places=9)

    def test_no_intersection_returns_empty_list(self):
        """AC-3: a plain (well-formed, non-self-intersecting) square returns []."""
        square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        self.assertEqual(_find_self_intersection_points_in_shape(square), [])

    def test_multipolygon_iterates_components(self):
        """A MultiPolygon with one self-intersecting + one clean component
        returns only the bad component's intersection point."""
        bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
        clean = Polygon([(10, 10), (11, 10), (11, 11), (10, 11)])
        mp = MultiPolygon([bowtie, clean])
        points = _find_self_intersection_points_in_shape(mp)
        self.assertEqual(len(points), 1)
        x, y = points[0]
        self.assertAlmostEqual(x, 0.5, places=9)
        self.assertAlmostEqual(y, 0.5, places=9)

    def test_multipolygon_two_intersections_under_cap(self):
        """AC-2: a MultiPolygon with two well-separated bow-ties yields two distinct points."""
        bowtie1 = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
        bowtie2 = Polygon([(10, 10), (11, 11), (11, 10), (10, 11)])
        mp = MultiPolygon([bowtie1, bowtie2])
        points = _find_self_intersection_points_in_shape(mp)
        self.assertEqual(len(points), 2)
        rounded = {(round(x, 6), round(y, 6)) for (x, y) in points}
        self.assertIn((0.5, 0.5), rounded)
        self.assertIn((10.5, 10.5), rounded)

    def test_post_makevalid_touching_triangles(self):
        """Regression: the post-makeValid shape of a bow-tie is a MultiPolygon
        of two triangles that *touch* at the original crossing point. The
        boundary's combined MultiLineString has ``is_simple == False`` (so the
        gate fires) but each triangle alone is clean. The finder must detect
        the cross-component touch and report the shared vertex.

        See DEC-10 for the algorithm fix that covers this case.
        """
        tri1 = Polygon([(0, 0), (1, 1), (0.5, 0.5)])
        tri2 = Polygon([(1, 1), (0.5, 0.5), (1, 0)])
        mp = MultiPolygon([tri1, tri2])
        points = _find_self_intersection_points_in_shape(mp)
        self.assertGreaterEqual(len(points), 1)
        rounded = {(round(x, 6), round(y, 6)) for (x, y) in points}
        # The triangles share two vertices: (1, 1) and (0.5, 0.5). Both are
        # legitimate cross-component touch points; the finder reports them
        # (after dedupe). The point of interest for the user is (0.5, 0.5).
        self.assertIn((0.5, 0.5), rounded)


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires Shapely + qgis.PyQt to import")
class TestDedupePoints(unittest.TestCase):
    """AC-2c: dedupe coincident points within the 1e-6 tolerance."""

    def test_dedupe_coincident_points(self):
        raw = [
            (0.0, 0.0),
            (1.0, 1.0),
            (0.0000005, 0.0000005),  # within 1e-6 of (0, 0)
            (2.0, 2.0),
        ]
        deduped = _dedupe_points(raw)
        self.assertEqual(len(deduped), 3)
        self.assertIn((0.0, 0.0), deduped)
        self.assertIn((1.0, 1.0), deduped)
        self.assertIn((2.0, 2.0), deduped)
        # The near-duplicate must NOT be retained
        self.assertNotIn((0.0000005, 0.0000005), deduped)

    def test_dedupe_preserves_distinct_points(self):
        raw = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        self.assertEqual(_dedupe_points(raw), raw)

    def test_dedupe_empty_list(self):
        self.assertEqual(_dedupe_points([]), [])


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires Shapely + qgis.PyQt to import")
class TestFormatSelfIntersectionMessage(unittest.TestCase):
    """Formatter-level tests — exercise the DEC-6 format and DEC-7 cap/overflow rules."""

    def test_formatter_empty_returns_base_string(self):
        """DEC-4 fallback: empty input → just the leading substring, no ' at:'."""
        self.assertEqual(
            _format_self_intersection_message([]),
            "Boundary has self-intersections",
        )

    def test_formatter_single_point_exact_substring(self):
        """AC-1 surface: 1 point → 6-decimal lon,lat, no trailing separator, no '(and K more)'."""
        msg = _format_self_intersection_message([(10.123456, -7.456789)])
        self.assertEqual(
            msg,
            "Boundary has self-intersections at: 10.123456,-7.456789",
        )

    def test_formatter_two_points_under_cap(self):
        """AC-2 surface: 2 points joined by ' | ' in input order."""
        msg = _format_self_intersection_message([(1.0, 2.0), (3.0, 4.0)])
        self.assertEqual(
            msg,
            "Boundary has self-intersections at: 1.000000,2.000000 | 3.000000,4.000000",
        )

    def test_formatter_eight_points_over_cap(self):
        """AC-2b: 8 points → first 5 rendered + ' (and 3 more)'."""
        points = [(float(i), float(i)) for i in range(8)]
        msg = _format_self_intersection_message(points)
        self.assertTrue(msg.startswith("Boundary has self-intersections at: "))
        self.assertTrue(msg.endswith(" (and 3 more)"))
        # First 5 points must be present
        for i in range(5):
            self.assertIn(f"{float(i):.6f},{float(i):.6f}", msg)
        # Last 3 points must NOT be present
        for i in range(5, 8):
            self.assertNotIn(f"{float(i):.6f},{float(i):.6f}", msg)


if __name__ == "__main__":
    unittest.main()
