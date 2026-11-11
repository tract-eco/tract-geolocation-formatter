"""
Unit tests for the pure land cover module (SPEC-landcover-overlap, Task 1).
Standard library only — no QGIS or GDAL required.

    python -m unittest tests.test_landcover -v
"""

import csv
import io
import os
import random
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from tract_geolocation_formatter import landcover as lc  # noqa: E402
from tract_geolocation_formatter.landcover import (  # noqa: E402
    BUILT_UP,
    CSV_FIELDNAMES,
    NO_COVERAGE,
    WATER,
    compute_landcover,
    csv_rows,
    geojson_properties,
    tile_name,
    tile_url,
    tiles_for_bboxes,
)


def _point_box(lon, lat, d=0.001):
    return (lon - d, lat - d, lon + d, lat + d)


class TileNameTests(unittest.TestCase):
    def test_hemispheres_and_padding(self):
        self.assertEqual(tile_name(36, 0), "N36E000")
        self.assertEqual(tile_name(-3, -60), "S03W060")
        self.assertEqual(tile_name(0, 9), "N00E009")
        self.assertEqual(tile_name(-36, 21), "S36E021")
        self.assertEqual(tile_name(51, -3), "N51W003")
        self.assertEqual(tile_name(-30, -120), "S30W120")

    def test_url(self):
        self.assertEqual(
            tile_url("N36E000"),
            "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
            "ESA_WorldCover_10m_2021_v200_N36E000_Map.tif",
        )


class TileResolverTests(unittest.TestCase):
    def test_ac4_known_tiles(self):
        """AC-4: bboxes around four known points map to their verified tiles."""
        self.assertEqual(tiles_for_bboxes([_point_box(0.5, 37)]), ["N36E000"])
        self.assertEqual(tiles_for_bboxes([_point_box(-59, -1.5)]), ["S03W060"])
        # Exactly on a corner (lon 9, lat 0): degenerate bbox → the cell starting there.
        self.assertEqual(tiles_for_bboxes([(9, 0, 9, 0)]), ["N00E009"])
        self.assertEqual(tiles_for_bboxes([_point_box(-1.5, 51.5)]), ["N51W003"])

    def test_ac5_edge_on_multiple_of_three(self):
        """AC-5: a max edge on lon 3 doesn't pull in E003; crossing it does."""
        self.assertEqual(tiles_for_bboxes([(1, 10, 3, 11)]), ["N09E000"])
        self.assertEqual(tiles_for_bboxes([(2.9, 10, 3.1, 11)]), ["N09E000", "N09E003"])
        # Same rule on latitude and in the southern/western hemispheres.
        self.assertEqual(tiles_for_bboxes([(-5, -6, -4, -3)]), ["S06W006"])
        self.assertEqual(tiles_for_bboxes([(-3, -2, -2, -1)]), ["S03W003"])

    def test_ac6_only_cells_touched_by_plots(self):
        """AC-6: two small plots 20° apart give only their two tiles."""
        tiles = tiles_for_bboxes([_point_box(0.15, 0.15), _point_box(20.15, 0.15)])
        self.assertEqual(tiles, ["N00E000", "N00E018"])

    def test_ac7_order_independent_and_sorted(self):
        """AC-7: same bboxes in any order → identical, sorted list."""
        boxes = [
            _point_box(0.5, 37), _point_box(-59, -1.5), _point_box(-1.5, 51.5),
            (2.9, 10, 3.1, 11), _point_box(20.15, 0.15),
        ]
        expected = tiles_for_bboxes(boxes)
        self.assertEqual(expected, sorted(expected))
        self.assertEqual(len(expected), len(set(expected)))
        rng = random.Random(7)
        for _ in range(10):
            shuffled = boxes[:]
            rng.shuffle(shuffled)
            self.assertEqual(tiles_for_bboxes(shuffled), expected)

    def test_bbox_spanning_four_cells(self):
        self.assertEqual(
            tiles_for_bboxes([(-0.1, 50.9, 0.1, 51.1)]),
            ["N48E000", "N48W003", "N51E000", "N51W003"],
        )

    def test_empty_input(self):
        self.assertEqual(tiles_for_bboxes([]), [])

    def test_poles_and_antimeridian_clamped(self):
        self.assertEqual(tiles_for_bboxes([(179.9, 89.9, 180, 90)]), ["N87E177"])
        self.assertEqual(tiles_for_bboxes([(-180, -90, -179.9, -89.9)]), ["S90W180"])


class ComputeTests(unittest.TestCase):
    def test_ac8_d6_formula(self):
        """AC-8: {NODATA:5, 10:15, 80:20}, 4000 m² → water 50.00 % / 2000.0 m²; no built-up."""
        hist = {0: {"NODATA": 5, 10: 15, 80: 20}}
        r = compute_landcover(
            {WATER: hist, BUILT_UP: hist}, {WATER: 80, BUILT_UP: 50}, {0: 4000.0}
        )
        pct, area = r.values[WATER][0]
        self.assertAlmostEqual(pct, 50.0)
        self.assertAlmostEqual(area, 2000.0)
        self.assertTrue(r.reported(WATER, 0))
        self.assertFalse(r.reported(BUILT_UP, 0))
        self.assertEqual(r.values[BUILT_UP][0], (0.0, 0.0))
        self.assertEqual(r.count(WATER), 1)
        self.assertEqual(r.count(BUILT_UP), 0)

    def test_ac9_one_pixel_is_reported_no_threshold(self):
        """AC-9: 1 water pixel of 400 is reported at 0.25 %; there is no threshold parameter."""
        r = compute_landcover({WATER: {0: {10: 399, 80: 1}}}, {WATER: 80}, {0: 1000.0})
        self.assertTrue(r.reported(WATER, 0))
        self.assertAlmostEqual(r.values[WATER][0][0], 0.25)
        rows = csv_rows(r, {0: 1}, {}, {}, {WATER: "src"})
        self.assertEqual(rows[0]["overlap_pct"], "0.25")
        for name in ("threshold", "min_pct", "MIN_PCT", "THRESHOLD"):
            self.assertFalse(hasattr(lc, name))
        import inspect
        self.assertNotIn("threshold", str(inspect.signature(compute_landcover)))

    def test_ac10_no_coverage_and_sub_pixel(self):
        """AC-10: total 0 → not assessed (None); a one-pixel water plot → 100 %."""
        hist = {0: {}, 1: {80: 1}}
        r = compute_landcover({WATER: hist}, {WATER: 80}, {0: 50.0, 1: 30.0})
        self.assertIsNone(r.values[WATER][0])
        self.assertEqual(r.no_coverage(WATER), [0])
        self.assertAlmostEqual(r.values[WATER][1][0], 100.0)
        self.assertAlmostEqual(r.values[WATER][1][1], 30.0)

    def test_plot_missing_from_histogram_is_no_coverage(self):
        r = compute_landcover({WATER: {}}, {WATER: 80}, {3: 100.0})
        self.assertIsNone(r.values[WATER][3])

    def test_nodata_counts_in_total(self):
        r = compute_landcover({WATER: {0: {"NODATA": 3, 80: 1}}}, {WATER: 80}, {0: 400.0})
        self.assertAlmostEqual(r.values[WATER][0][0], 25.0)

    def test_only_configured_classes_computed(self):
        r = compute_landcover({WATER: {0: {80: 1}}}, {WATER: 80}, {0: 1.0})
        self.assertEqual(r.classes, (WATER,))

    def test_plot_order_respected(self):
        r = compute_landcover({WATER: {}}, {WATER: 80}, {2: 1, 0: 1, 1: 1}, plot_order=[2, 0, 1])
        self.assertEqual(r.plot_order, [2, 0, 1])


class GeojsonPropertiesTests(unittest.TestCase):
    def _result(self):
        hist = {
            0: {"NODATA": 5, 10: 15, 80: 20},   # water 50 %
            1: {10: 3, 50: 1},                  # built-up 25 %
            2: {},                              # not assessed
            3: {10: 7},                         # nothing
        }
        return compute_landcover(
            {WATER: hist, BUILT_UP: hist},
            {WATER: 80, BUILT_UP: 50},
            {0: 4000.0, 1: 1234.56, 2: 99.0, 3: 10.0},
            plot_order=[0, 1, 2, 3],
        )

    def test_values_zero_and_rounding(self):
        props = geojson_properties(self._result())
        self.assertEqual(props[0], {
            "WaterOverlap_m2": 2000.0, "WaterOverlap_pct": 50.0,
            "BuiltUpOverlap_m2": 0.0, "BuiltUpOverlap_pct": 0.0,
        })
        self.assertEqual(props[1]["BuiltUpOverlap_m2"], 308.6)
        self.assertEqual(props[1]["BuiltUpOverlap_pct"], 25.0)
        self.assertEqual(props[3]["WaterOverlap_pct"], 0.0)

    def test_ac31_no_coverage_is_null(self):
        """AC-31: a no_coverage plot gets null in all four fields."""
        props = geojson_properties(self._result())
        self.assertEqual(set(props[2].values()), {None})
        self.assertEqual(len(props[2]), 4)

    def test_field_order_water_then_built_up(self):
        props = geojson_properties(self._result())
        self.assertEqual(list(props[0]), list(lc.ALL_FIELD_NAMES))

    def test_only_classes_that_ran(self):
        r = compute_landcover({WATER: {0: {80: 1}}}, {WATER: 80}, {0: 1.0})
        self.assertEqual(list(geojson_properties(r)[0]), ["WaterOverlap_m2", "WaterOverlap_pct"])


class CsvRowsTests(unittest.TestCase):
    def _rows(self):
        hist = {
            0: {"NODATA": 5, 10: 15, 80: 20},
            1: {80: 2, 50: 2},
            2: {},
            3: {10: 7},
        }
        r = compute_landcover(
            {WATER: hist, BUILT_UP: hist},
            {WATER: 80, BUILT_UP: 50},
            {0: 4000.0, 1: 100.04, 2: 99.0, 3: 10.0},
            plot_order=[0, 1, 2, 3],
        )
        return csv_rows(
            r,
            feature_ids={0: 10, 1: 11, 2: 12, 3: 13},
            node_ids={0: "N1", 1: "N1", 2: "N2", 3: "N3"},
            plot_ids={0: "P1", 1: None, 2: "P3", 3: "P4"},
            sources={WATER: lc.SOURCE_FETCH, BUILT_UP: lc.SOURCE_FETCH},
        )

    def test_columns_order_and_rounding(self):
        rows = self._rows()
        self.assertEqual(list(rows[0]), CSV_FIELDNAMES)
        self.assertEqual(rows[0], {
            "feature_id": 10, "NodeID": "N1", "PlotID": "P1", "class": WATER,
            "overlap_area_m2": "2000.0", "overlap_pct": "50.00",
            "plot_area_m2": "4000.0", "source": "ESA WorldCover 2021 v200",
        })

    def test_row_order_and_classes(self):
        rows = self._rows()
        self.assertEqual(
            [(r["feature_id"], r["class"]) for r in rows],
            [(10, WATER), (11, WATER), (11, BUILT_UP), (12, NO_COVERAGE)],
        )

    def test_empty_plot_id_and_no_coverage_blanks(self):
        rows = self._rows()
        self.assertEqual(rows[1]["PlotID"], "")
        na = rows[3]
        self.assertEqual((na["overlap_area_m2"], na["overlap_pct"]), ("", ""))
        self.assertEqual(na["plot_area_m2"], "99.0")

    def test_no_coverage_one_row_per_distinct_source(self):
        r = compute_landcover(
            {WATER: {0: {}}, BUILT_UP: {0: {}}}, {WATER: 1, BUILT_UP: 2}, {0: 5.0}
        )
        same = csv_rows(r, {0: 1}, {}, {}, {WATER: "A, band 1, value 1", BUILT_UP: "A, band 1, value 1"})
        self.assertEqual(len(same), 1)
        diff = csv_rows(r, {0: 1}, {}, {}, {WATER: "A, band 1, value 1", BUILT_UP: "B, band 2, value 2"})
        self.assertEqual([x["source"] for x in diff], ["A, band 1, value 1", "B, band 2, value 2"])

    def test_no_coverage_dedup_by_coverage_source(self):
        """Same raster and band, different class values → one no_coverage row (DEC-14)."""
        r = compute_landcover(
            {WATER: {0: {}}, BUILT_UP: {0: {}}}, {WATER: 80, BUILT_UP: 50}, {0: 5.0}
        )
        rows = csv_rows(
            r, {0: 1}, {}, {}, {WATER: "lc, band 1, value 80", BUILT_UP: "lc, band 1, value 50"},
            coverage_sources={WATER: "lc, band 1", BUILT_UP: "lc, band 1"},
        )
        self.assertEqual([(x["class"], x["source"]) for x in rows], [(NO_COVERAGE, "lc, band 1")])
        self.assertEqual(lc.project_coverage_label("lc", 2), "lc, band 2")

    def test_no_overlap_gives_no_rows(self):
        r = compute_landcover({WATER: {0: {10: 4}}}, {WATER: 80}, {0: 5.0})
        self.assertEqual(csv_rows(r, {0: 1}, {}, {}, {WATER: "s"}), [])

    def test_ac28_deterministic_csv_bytes(self):
        """AC-28 (unit level): the same input gives byte-identical CSV text."""
        def render():
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=CSV_FIELDNAMES)
            w.writeheader()
            for row in self._rows():
                w.writerow(row)
            return buf.getvalue()
        self.assertEqual(render(), render())


class OutcomeTests(unittest.TestCase):
    def test_failed_outcome(self):
        o = lc.LandcoverOutcome.failed("internal error")
        self.assertEqual(o.statuses, {WATER: lc.STATUS_NOT_RUN, BUILT_UP: lc.STATUS_NOT_RUN})
        self.assertEqual(o.reasons[WATER], "internal error")
        self.assertEqual(o.classes_ran(), ())

    def test_classes_ran(self):
        o = lc.LandcoverOutcome(statuses={WATER: lc.STATUS_RAN, BUILT_UP: lc.STATUS_NOT_CHECKED})
        self.assertEqual(o.classes_ran(), (WATER,))

    def test_config_enabled_and_sources(self):
        """DEC-21: the check is on when any class is ticked; sources are per class."""
        cfg = lc.LandcoverConfig(classes={
            WATER: lc.ClassSpec(enabled=True, source=lc.SOURCE_PROJECT, layer_id="L"),
            BUILT_UP: lc.ClassSpec(enabled=False),
        })
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.classes_with_source(lc.SOURCE_PROJECT), [WATER])
        self.assertEqual(cfg.classes_with_source(lc.SOURCE_WORLDCOVER), [])
        self.assertFalse(lc.LandcoverConfig(classes={WATER: lc.ClassSpec()}).enabled)
        self.assertFalse(lc.LandcoverConfig().enabled)

    def test_project_source_label(self):
        self.assertEqual(lc.project_source_label("lc.tif", 2, 7), "lc.tif, band 2, value 7")


class PurityTests(unittest.TestCase):
    def test_no_qgis_or_gdal_imports(self):
        path = os.path.join(_REPO_ROOT, "tract_geolocation_formatter", "landcover.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for banned in ("import qgis", "from qgis", "osgeo", "import shapely", "from shapely"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
