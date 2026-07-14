"""
Unit tests for hole fixing (SPEC-fix-holes). Pure Shapely — no QGIS required.

    python -m pytest tests/test_hole_fixing.py -v
    python -m unittest tests.test_hole_fixing -v
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

try:
    from shapely.geometry import MultiPolygon, Polygon
    # Guard against a stubbed Shapely (another test module may install fakes in
    # sys.modules): confirm this is the real library by checking a known area.
    if Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]).area != 1.0:
        raise ImportError("shapely appears stubbed, not real")
    SHAPELY = True
except Exception:
    SHAPELY = False

if SHAPELY:
    from tract_geolocation_formatter.hole_fixing import (
        cut_holes,
        fill_holes,
        fix_holes,
        has_holes,
    )


# A 10x10 square with a 2x2 hole in the middle -> a donut.
_EXTERIOR = [(0, 0), (10, 0), (10, 10), (0, 10)]
_HOLE = [(4, 4), (6, 4), (6, 6), (4, 6)]


def _donut():
    return Polygon(_EXTERIOR, [_HOLE])


def _two_holes():
    # 20x10 with two separate 2x2 holes.
    ext = [(0, 0), (20, 0), (20, 10), (0, 10)]
    h1 = [(3, 4), (5, 4), (5, 6), (3, 6)]
    h2 = [(14, 4), (16, 4), (16, 6), (14, 6)]
    return Polygon(ext, [h1, h2])


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestHasHoles(unittest.TestCase):

    def test_donut_has_holes(self):
        self.assertTrue(has_holes(_donut()))

    def test_simple_polygon_no_holes(self):
        self.assertFalse(has_holes(Polygon(_EXTERIOR)))

    def test_multipolygon_no_holes(self):
        mp = MultiPolygon([Polygon(_EXTERIOR), Polygon([(20, 0), (25, 0), (25, 5)])])
        self.assertFalse(has_holes(mp))


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestFill(unittest.TestCase):

    def test_fill_removes_holes(self):
        filled, notes = fill_holes(_donut())
        self.assertFalse(has_holes(filled))
        self.assertTrue(notes)

    def test_fill_grows_area_by_hole(self):
        filled, _ = fill_holes(_donut())
        # exterior 100, hole 4 -> donut area 96, filled area 100.
        self.assertAlmostEqual(filled.area, 100.0, places=6)


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestCut(unittest.TestCase):

    def test_cut_single_donut(self):
        donut = _donut()
        result, parts, _notes = cut_holes(donut)
        self.assertFalse(has_holes(result))
        self.assertTrue(result.is_valid)
        # Slit opens the hole into one valid polygon (not a multipart split).
        self.assertGreaterEqual(parts, 1)

    def test_cut_preserves_area(self):
        donut = _donut()
        result, _parts, _notes = cut_holes(donut)
        # donut area = 100 - 4 = 96; the slit removes only a negligible strip.
        self.assertAlmostEqual(result.area, 96.0, places=3)
        # Area is lost (never gained) — the opposite of fill.
        self.assertLessEqual(result.area, 96.0 + 1e-9)

    def test_cut_multiple_holes(self):
        result, _parts, _notes = cut_holes(_two_holes())
        self.assertFalse(has_holes(result))
        self.assertTrue(result.is_valid)
        self.assertAlmostEqual(result.area, _two_holes().area, places=3)

    def test_cut_multipolygon_one_part_holed(self):
        holed = _donut()
        clean = Polygon([(20, 0), (30, 0), (30, 10), (20, 10)])
        mp = MultiPolygon([holed, clean])
        result, _parts, _notes = cut_holes(mp)
        self.assertFalse(has_holes(result))
        self.assertTrue(result.is_valid)
        self.assertAlmostEqual(result.area, mp.area, places=3)

    def test_cut_hole_near_boundary(self):
        # Hole close to the left edge — nearest exterior point is very near.
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)],
                       [[(0.5, 4), (2, 4), (2, 6), (0.5, 6)]])
        result, _parts, notes = cut_holes(poly)
        self.assertFalse(has_holes(result), notes)
        self.assertTrue(result.is_valid)

    def test_cut_irregular_polygon(self):
        # Non-axis-aligned L-ish polygon with a hole.
        poly = Polygon(
            [(0, 0), (12, 1), (11, 8), (5, 9), (1, 6)],
            [[(4, 3), (6, 3), (6, 5), (4, 5)]],
        )
        result, _parts, notes = cut_holes(poly)
        self.assertFalse(has_holes(result), notes)
        self.assertTrue(result.is_valid)

    def test_cut_degree_scale_truncated(self):
        # Realistic EPSG:4326 donut with 6-decimal coords.
        poly = Polygon(
            [(19.000000, 47.000000), (19.002000, 47.000000),
             (19.002000, 47.002000), (19.000000, 47.002000)],
            [[(19.000800, 47.000800), (19.001200, 47.000800),
              (19.001200, 47.001200), (19.000800, 47.001200)]],
        )
        result, _parts, notes = cut_holes(poly)
        self.assertFalse(has_holes(result), notes)
        self.assertTrue(result.is_valid)

    def test_cut_no_holes_is_noop(self):
        simple = Polygon(_EXTERIOR)
        result, parts, notes = cut_holes(simple)
        self.assertFalse(has_holes(result))
        self.assertEqual(parts, 1)
        self.assertEqual(notes, [])


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestFixHolesDispatch(unittest.TestCase):

    def test_fill_dispatch_resolved(self):
        new_geom, _parts, _notes, resolved = fix_holes(_donut(), "fill")
        self.assertTrue(resolved)
        self.assertFalse(has_holes(new_geom))

    def test_cut_dispatch_resolved(self):
        new_geom, parts, _notes, resolved = fix_holes(_donut(), "cut")
        self.assertTrue(resolved)
        self.assertFalse(has_holes(new_geom))
        self.assertGreaterEqual(parts, 1)

    def test_unknown_method_not_resolved(self):
        new_geom, parts, notes, resolved = fix_holes(_donut(), "bogus")
        self.assertFalse(resolved)
        self.assertEqual(parts, 0)
        self.assertTrue(notes)

    def test_cut_areas_differ_from_fill(self):
        cut_geom, _p, _n, _r = fix_holes(_donut(), "cut")
        fill_geom, _p2, _n2, _r2 = fix_holes(_donut(), "fill")
        # cut preserves (96), fill grows (100)
        self.assertLess(cut_geom.area, fill_geom.area)


if __name__ == "__main__":
    unittest.main()
