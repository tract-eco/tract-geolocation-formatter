"""
Unit tests for polygon overlap detection (GH-12). Pure Shapely — no QGIS required.

    python -m pytest tests/test_overlaps.py -v
    python -m unittest tests.test_overlaps -v
"""

import json
import math
import os
import random
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

try:
    from shapely.geometry import MultiPolygon, Polygon, box, shape
    # Guard against a stubbed Shapely (another test module may install fakes in
    # sys.modules): confirm this is the real library by checking a known area.
    if Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]).area != 1.0:
        raise ImportError("shapely appears stubbed, not real")
    SHAPELY = True
except Exception:
    SHAPELY = False

if SHAPELY:
    from tract_geolocation_formatter.overlaps import (
        OVERLAP_PROPERTIES,
        apply_feature_fixes,
        candidate_pairs,
        dissolve_part_overlaps,
        find_feature_overlaps,
        find_part_overlaps,
        overlaps_feature_collection,
        residual_overlap_pct,
        would_remove_last_plot,
    )


def _item(index, geom, node_id="N1", plot_id=None):
    return {"index": index, "node_id": node_id, "plot_id": plot_id or "P%d" % index, "geom": geom}


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestPredicate(unittest.TestCase):
    """AC-2 to AC-7."""

    def test_shared_edge_or_vertex_is_not_overlap(self):  # AC-2
        a = box(0, 0, 10, 10)
        edge = box(10, 0, 20, 10)
        vertex = box(10, 10, 20, 20)
        items = [_item(0, a), _item(1, edge), _item(2, vertex)]
        self.assertEqual(find_feature_overlaps(items, min_pct=0.0), [])

    def test_parts_sharing_edge_not_overlap(self):  # AC-2
        mp = MultiPolygon([box(0, 0, 1, 1), box(1, 0, 2, 1)])
        self.assertEqual(find_part_overlaps(mp, min_pct=0.0), [])

    def test_partial_same_node_is_b(self):  # AC-3
        a = box(0, 0, 10, 10)
        b = box(9.5, 0, 19.5, 10)  # 0.5 x 10 = 5 of 100 -> 5 %
        [f] = find_feature_overlaps([_item(0, a), _item(1, b)], min_pct=1.0)
        self.assertEqual((f.category, f.kind), ("B", "partial"))
        self.assertAlmostEqual(f.area, 5.0, places=9)
        self.assertAlmostEqual(f.pct_of_smaller, 5.0, delta=1e-6)
        self.assertFalse(f.below_threshold)
        self.assertIsNone(f.container)
        self.assertAlmostEqual(f.overlap_geom.area, 5.0, places=9)

    def test_partial_cross_node_is_c(self):  # AC-3
        a = box(0, 0, 10, 10)
        b = box(9.5, 0, 19.5, 10)
        [f] = find_feature_overlaps([_item(0, a, "N1"), _item(1, b, "N2")])
        self.assertEqual(f.category, "C")

    def test_pct_uses_smaller_plot(self):
        a = box(0, 0, 100, 100)
        b = box(99, 0, 109, 10)  # overlap 1 x 10 = 10, b area 100 -> 10 %
        [f] = find_feature_overlaps([_item(0, a), _item(1, b)])
        self.assertAlmostEqual(f.pct_of_smaller, 10.0, delta=1e-6)

    def test_containment(self):  # AC-4
        a = box(0, 0, 10, 10)
        b = box(0, 0, 2, 2)  # touches a's boundary from inside
        [f] = find_feature_overlaps([_item(0, a), _item(1, b)])
        self.assertEqual(f.kind, "containment")
        self.assertEqual((f.container, f.contained), (0, 1))
        self.assertEqual(f.pct_of_smaller, 100.0)

    def test_containment_container_later_in_order(self):  # AC-4
        small = box(2, 2, 3, 3)
        big = box(0, 0, 10, 10)
        [f] = find_feature_overlaps([_item(0, small), _item(1, big)])
        self.assertEqual((f.index_a, f.index_b), (0, 1))
        self.assertEqual((f.container, f.contained), (1, 0))

    def test_identical(self):  # AC-4
        a = box(0, 0, 10, 10)
        [f] = find_feature_overlaps([_item(0, a), _item(1, box(0, 0, 10, 10))])
        self.assertEqual(f.kind, "identical")
        self.assertEqual((f.container, f.contained), (0, 1))
        self.assertEqual(f.pct_of_smaller, 100.0)

    def test_custom_area_fn(self):  # AC-5
        a = box(0, 0, 10, 10)
        b = box(9.5, 0, 19.5, 10)
        [f] = find_feature_overlaps([_item(0, a), _item(1, b)], area_fn=lambda g: 2 * g.area)
        self.assertAlmostEqual(f.area, 10.0, places=9)
        self.assertAlmostEqual(f.pct_of_smaller, 5.0, delta=1e-6)

    def test_plot_areas_used_for_pct(self):
        a = box(0, 0, 10, 10)
        b = box(9.5, 0, 19.5, 10)
        [f] = find_feature_overlaps(
            [_item(0, a), _item(1, b)], plot_areas={0: 50.0, 1: 200.0}
        )
        self.assertAlmostEqual(f.pct_of_smaller, 10.0, delta=1e-6)

    def test_threshold(self):  # AC-6
        base = box(0, 0, 10, 10)  # area 100
        half = box(9.95, 0, 19.95, 10)  # 0.05 x 10 = 0.5 %
        one = box(-99, 20, 1, 21)  # vs box(0,20,100,21): 1 x 1 = exactly 1.0 %
        inner = box(40, 40, 41, 41)
        items = [
            _item(0, base),
            _item(1, half),
            _item(2, box(0, 20, 100, 21)),
            _item(3, one),
            _item(4, box(39, 39, 50, 50)),
            _item(5, inner),
        ]
        by_pair = {(f.index_a, f.index_b): f for f in find_feature_overlaps(items, min_pct=1.0)}
        self.assertTrue(by_pair[(0, 1)].below_threshold)
        self.assertEqual(by_pair[(2, 3)].pct_of_smaller, 1.0)
        self.assertFalse(by_pair[(2, 3)].below_threshold)
        self.assertFalse(by_pair[(4, 5)].below_threshold)

        zero = find_feature_overlaps(items, min_pct=0.0)
        self.assertEqual(len(zero), 3)
        self.assertTrue(all(not f.below_threshold for f in zero))

    def test_part_threshold(self):  # AC-6, AC-13 (threshold logic)
        mp = MultiPolygon(
            [
                box(0, 0, 10, 10),
                box(9.5, 0, 19.5, 10),  # 5 % of part 0/1
                box(30, 0, 40, 10),
                box(39.95, 0, 49.95, 10),  # 0.5 % of part 2/3
            ]
        )
        found = {(f.i, f.j): f for f in find_part_overlaps(mp, min_pct=1.0)}
        self.assertEqual(set(found), {(0, 1), (2, 3)})
        self.assertFalse(found[(0, 1)].below_threshold)
        self.assertTrue(found[(2, 3)].below_threshold)
        self.assertAlmostEqual(found[(2, 3)].pct_of_smaller, 0.5, delta=1e-6)
        self.assertTrue(all(not f.below_threshold for f in find_part_overlaps(mp, min_pct=0.0)))

    def test_order_and_determinism(self):  # AC-7
        items = [
            _item(0, box(0, 0, 10, 10), "N1"),
            _item(1, box(5, 0, 15, 10), "N2"),  # C with 0
            _item(2, box(8, 0, 18, 10), "N1"),  # B with 0, C with 1
            _item(3, box(100, 0, 110, 10), "N3"),
            _item(4, box(105, 0, 115, 10), "N3"),  # B with 3
        ]
        first = find_feature_overlaps(items)
        keys = [(f.category, f.index_a, f.index_b) for f in first]
        self.assertEqual(keys, [("B", 0, 2), ("B", 3, 4), ("C", 0, 1), ("C", 1, 2)])
        second = find_feature_overlaps(list(reversed(items)))
        self.assertEqual(
            [(f.category, f.index_a, f.index_b, f.overlap_geom.wkt) for f in first],
            [(f.category, f.index_a, f.index_b, f.overlap_geom.wkt) for f in second],
        )

    def test_node_id_none_matches_none(self):
        a, b = box(0, 0, 10, 10), box(5, 0, 15, 10)
        [f] = find_feature_overlaps([_item(0, a, None), _item(1, b, None)])
        self.assertEqual(f.category, "B")

    def test_progress_called(self):
        calls = []
        items = [_item(k, box(k, 0, k + 2, 2)) for k in range(10)]
        find_feature_overlaps(items, progress=lambda d, t: calls.append((d, t)))
        self.assertTrue(calls)
        self.assertEqual(calls[-1][0], calls[-1][1])


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestCandidatePairs(unittest.TestCase):
    """AC-8."""

    @staticmethod
    def _brute(bounds):
        out = set()
        for i in range(len(bounds)):
            for j in range(i + 1, len(bounds)):
                a, b = bounds[i], bounds[j]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    out.add((i, j))
        return out

    def test_matches_brute_force(self):
        rng = random.Random(42)
        bounds = []
        for _ in range(500):
            x, y = rng.uniform(0, 100), rng.uniform(0, 100)
            bounds.append((x, y, x + rng.uniform(0, 8), y + rng.uniform(0, 8)))
        # A few exact touches.
        bounds += [(200, 0, 210, 10), (210, 0, 220, 10), (220, 10, 230, 20)]
        pairs = candidate_pairs(bounds)
        self.assertEqual(set(pairs), self._brute(bounds))
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertEqual(pairs, sorted(pairs))
        self.assertEqual(pairs, candidate_pairs(bounds))

    def test_touching_included_and_empty_skipped(self):
        bounds = [(0, 0, 1, 1), (1, 1, 2, 2), (), (5, 5, 6, 6)]
        self.assertEqual(candidate_pairs(bounds), [(0, 1)])


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestPartOverlaps(unittest.TestCase):
    """AC-9, AC-10."""

    def test_overlapping_boxes(self):  # AC-9
        mp = MultiPolygon([box(0, 0, 2, 2), box(1, 1, 3, 3)])
        [f] = find_part_overlaps(mp)
        self.assertEqual((f.i, f.j), (0, 1))
        self.assertAlmostEqual(f.area, 1.0, places=9)
        self.assertAlmostEqual(f.pct_of_smaller, 25.0, delta=1e-6)

    def test_contained_part(self):  # AC-9
        mp = MultiPolygon([box(0, 0, 10, 10), box(2, 2, 3, 3)])
        [f] = find_part_overlaps(mp)
        self.assertEqual(f.pct_of_smaller, 100.0)

    def test_none_for_disjoint_edge_or_polygon(self):  # AC-9
        self.assertEqual(find_part_overlaps(MultiPolygon([box(0, 0, 1, 1), box(5, 5, 6, 6)])), [])
        self.assertEqual(find_part_overlaps(MultiPolygon([box(0, 0, 1, 1), box(1, 0, 2, 1)])), [])
        self.assertEqual(find_part_overlaps(box(0, 0, 1, 1)), [])

    def test_dissolve(self):  # AC-10
        mp = MultiPolygon([box(0, 0, 2, 2), box(1, 1, 3, 3)])
        self.assertAlmostEqual(mp.area, 8.0)
        out = dissolve_part_overlaps(mp)
        self.assertTrue(out.is_valid)
        self.assertAlmostEqual(out.area, 7.0, places=9)

    def test_dissolve_keeps_disjoint_part(self):  # AC-10
        far = box(10, 10, 11, 11)
        mp = MultiPolygon([box(0, 0, 2, 2), box(1, 1, 3, 3), far])
        out = dissolve_part_overlaps(mp)
        self.assertTrue(out.is_valid)
        self.assertAlmostEqual(out.area, 8.0, places=9)
        self.assertTrue(any(g.equals(far) for g in out.geoms))


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestHelpers(unittest.TestCase):

    def test_residual_overlap_pct(self):
        a = box(0, 0, 10, 10)
        self.assertEqual(residual_overlap_pct(a, box(10, 0, 20, 10)), 0.0)
        self.assertEqual(residual_overlap_pct(a, box(50, 0, 60, 10)), 0.0)
        self.assertAlmostEqual(residual_overlap_pct(a, box(9.99, 0, 19.99, 10)), 0.1, places=6)

    def test_would_remove_last_plot(self):
        node_counts = {"N1": 2, "N2": 1, "N3": 3}
        node_ids = {0: "N1", 1: "N1", 2: "N2", 3: "N3", 4: "N3"}
        self.assertEqual(would_remove_last_plot(node_counts, node_ids, set()), set())
        self.assertEqual(would_remove_last_plot(node_counts, node_ids, {0}), set())
        self.assertEqual(would_remove_last_plot(node_counts, node_ids, {0, 1}), {0, 1})
        self.assertEqual(would_remove_last_plot(node_counts, node_ids, {2, 3}), {2})


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestOverlapsFeatureCollection(unittest.TestCase):

    def test_property_order_rounding_and_geometry(self):
        rec = {
            "action": "clipped_a",
            "category": "C",
            "type": "partial",
            "feature_a": "1 (P1)",
            "feature_b": "2 (P2)",
            "NodeID_a": "N1",
            "NodeID_b": "N2",
            "PlotID_a": "P1",
            "PlotID_b": "P2",
            "area_m2": 12.3456,
            "pct_of_smaller": 1.23456,
            "below_threshold": 0,
            "geometry": box(0.1234567, 0, 1.9999999, 1),
        }
        fc = overlaps_feature_collection([rec])
        fc = json.loads(json.dumps(fc))  # serialisable
        self.assertEqual(fc["type"], "FeatureCollection")
        self.assertIn("crs", fc)
        [feat] = fc["features"]
        self.assertEqual(list(feat["properties"]), list(OVERLAP_PROPERTIES))
        props = feat["properties"]
        self.assertIsNone(props["part_a"])
        self.assertEqual(props["area_m2"], 12.35)
        self.assertEqual(props["pct_of_smaller"], 1.235)
        self.assertIs(props["below_threshold"], False)
        xs = [c[0] for c in feat["geometry"]["coordinates"][0]]
        self.assertIn(0.123456, xs)
        self.assertIn(1.999999, xs)
        self.assertAlmostEqual(shape(feat["geometry"]).area, 1.876543, places=6)

    def test_below_threshold_true(self):
        fc = overlaps_feature_collection(
            [{"category": "A", "part_a": 1, "part_b": 2, "below_threshold": True,
              "geometry": box(0, 0, 1, 1)}]
        )
        props = fc["features"][0]["properties"]
        self.assertIs(props["below_threshold"], True)
        self.assertEqual((props["part_a"], props["part_b"]), (1, 2))

    def test_empty(self):
        self.assertEqual(overlaps_feature_collection([])["features"], [])


@unittest.skipUnless(SHAPELY, "Requires Shapely")
class TestApplyFeatureFixes(unittest.TestCase):
    """AC-20 to AC-25."""

    @staticmethod
    def _run(items, clip=True, containment=None, cross=None, skip_clip=frozenset(), min_pct=1.0):
        findings = find_feature_overlaps(items, min_pct=min_pct)
        return findings, apply_feature_fixes(
            items, findings, clip, containment or {}, cross or {}, skip_clip=skip_clip
        )

    @staticmethod
    def _no_overlap(geoms):
        geoms = list(geoms)
        for i in range(len(geoms)):
            for j in range(i + 1, len(geoms)):
                if geoms[i].relate_pattern(geoms[j], "2********"):
                    return False
        return True

    def test_same_node_smaller_clipped(self):  # AC-20
        big = box(0, 0, 10, 10)
        small = box(8, 0, 13, 5)
        items = [_item(0, small), _item(1, big)]
        _, (new, deleted, actions) = self._run(items)
        self.assertEqual(set(new), {0})
        self.assertEqual(deleted, set())
        self.assertEqual(actions, {(0, 1): "clipped_a"})
        self.assertAlmostEqual(new[0].area, 15.0, places=9)
        self.assertTrue(self._no_overlap([new[0], big]))

    def test_chain_of_three(self):  # AC-21
        a = box(0, 0, 10, 10)  # 100
        b = box(8, 0, 16, 8)  # 64; overlaps a
        c = box(7, 6, 13, 12)  # 36; overlaps a and b
        items = [_item(0, c), _item(1, b), _item(2, a)]
        findings, (new, deleted, actions) = self._run(items)
        self.assertEqual(len(findings), 3)
        self.assertNotIn(2, new)  # largest unchanged
        self.assertEqual(set(new), {0, 1})
        final = {0: new[0], 1: new[1], 2: a}
        self.assertTrue(self._no_overlap(final.values()))
        self.assertEqual(
            actions, {(0, 1): "clipped_a", (0, 2): "clipped_a", (1, 2): "clipped_a"}
        )

    def test_tie_broken_by_plot_id(self):  # AC-21, DEC-5
        p1 = box(0, 0, 10, 10)
        p2 = box(5, 0, 15, 10)
        # Output order puts "B" first; lower PlotID "A" keeps the overlap.
        items = [_item(0, p1, plot_id="B"), _item(1, p2, plot_id="A")]
        _, (new, _, actions) = self._run(items)
        self.assertEqual(set(new), {0})
        self.assertEqual(actions, {(0, 1): "clipped_a"})

    def test_tie_same_plot_id_broken_by_index(self):
        items = [_item(0, box(0, 0, 10, 10), plot_id="X"), _item(1, box(5, 0, 15, 10), plot_id="X")]
        _, (new, _, _) = self._run(items)
        self.assertEqual(set(new), {1})

    def test_clip_same_node_off(self):  # AC-22
        items = [_item(0, box(0, 0, 10, 10)), _item(1, box(8, 0, 13, 5))]
        _, (new, deleted, actions) = self._run(items, clip=False)
        self.assertEqual((new, deleted), ({}, set()))
        self.assertEqual(actions, {(0, 1): "kept"})

    def test_containment_actions(self):  # AC-23
        items = [_item(0, box(0, 0, 10, 10)), _item(1, box(2, 2, 4, 4))]
        for choice, expected, action in (
            ("delete_contained", {1}, "deleted_b"),
            ("delete_container", {0}, "deleted_a"),
            ("keep", set(), "kept"),
        ):
            _, (new, deleted, actions) = self._run(items, containment={(0, 1): choice})
            self.assertEqual(deleted, expected, choice)
            self.assertEqual(actions, {(0, 1): action}, choice)
            self.assertEqual(new, {})

    def test_containment_defaults_to_keep(self):
        items = [_item(0, box(0, 0, 10, 10)), _item(1, box(2, 2, 4, 4))]
        _, (_, deleted, actions) = self._run(items)
        self.assertEqual(deleted, set())
        self.assertEqual(actions, {(0, 1): "kept"})

    def test_identical_keeps_earlier(self):  # AC-24
        items = [_item(0, box(0, 0, 10, 10)), _item(1, box(0, 0, 10, 10))]
        _, (_, deleted, actions) = self._run(items, containment={(0, 1): "delete_contained"})
        self.assertEqual(deleted, {1})
        self.assertEqual(actions, {(0, 1): "deleted_b"})

    def test_cross_node_actions(self):  # AC-25
        a = box(0, 0, 10, 10)
        b = box(8, 0, 18, 10)
        items = [_item(0, a, "N1"), _item(1, b, "N2")]
        _, (new, _, actions) = self._run(items, cross={(0, 1): "keep"})
        self.assertEqual((new, actions), ({}, {(0, 1): "kept"}))
        _, (new, _, actions) = self._run(items, cross={(0, 1): "remove_from_a"})
        self.assertEqual(set(new), {0})
        self.assertAlmostEqual(new[0].area, 80.0, places=9)
        self.assertEqual(actions, {(0, 1): "clipped_a"})
        _, (new, _, actions) = self._run(items, cross={(0, 1): "remove_from_b"})
        self.assertEqual(set(new), {1})
        self.assertEqual(actions, {(0, 1): "clipped_b"})

    def test_cross_node_pair_with_deleted_plot_skipped(self):  # AC-25
        big = box(0, 0, 10, 10)
        inner = box(1, 1, 3, 3)
        other = box(2, 0, 20, 2)  # different NodeID, overlaps both
        items = [_item(0, big, "N1"), _item(1, inner, "N1"), _item(2, other, "N2")]
        findings, (new, deleted, actions) = self._run(
            items,
            containment={(0, 1): "delete_contained"},
            cross={(0, 2): "remove_from_b", (1, 2): "remove_from_a"},
        )
        self.assertEqual(deleted, {1})
        self.assertNotIn((1, 2), actions)
        self.assertEqual(actions[(0, 2)], "clipped_b")
        self.assertEqual(set(new), {2})

    def test_below_threshold_never_applied(self):  # AC-25
        a = box(0, 0, 10, 10)
        b = box(9.95, 0, 19.95, 10)  # 0.5 %
        items = [_item(0, a, "N1"), _item(1, b, "N2")]
        _, (new, deleted, actions) = self._run(items, cross={(0, 1): "remove_from_a"})
        self.assertEqual((new, deleted, actions), ({}, set(), {}))
        same = [_item(0, a), _item(1, b)]
        _, (new, _, actions) = self._run(same)
        self.assertEqual((new, actions), ({}, {}))

    def test_skip_clip_for_z(self):  # FR-7
        items = [_item(0, box(0, 0, 10, 10), "N1"), _item(1, box(8, 0, 18, 10), "N2")]
        _, (new, _, actions) = self._run(
            items, cross={(0, 1): "remove_from_a"}, skip_clip={0}
        )
        self.assertEqual((new, actions), ({}, {(0, 1): "skipped_z"}))

    def test_same_node_per_pair_choices(self):
        """A dict of per-pair choices replaces the all-or-nothing same-NodeID clip."""
        big = box(0, 0, 10, 10)
        small = box(8, 0, 14, 6)
        items = [_item(0, big, "N1"), _item(1, small, "N1")]
        _, (new, _, actions) = self._run(items, clip={(0, 1): "remove_from_a"})
        self.assertEqual(actions, {(0, 1): "clipped_a"})
        self.assertAlmostEqual(new[0].area, 100.0 - 12.0)
        _, (new, _, actions) = self._run(items, clip={(0, 1): "remove_from_b"})
        self.assertEqual(actions, {(0, 1): "clipped_b"})
        self.assertAlmostEqual(new[1].area, 36.0 - 12.0)
        _, (new, _, actions) = self._run(items, clip={(0, 1): "keep"})
        self.assertEqual((new, actions), ({}, {(0, 1): "kept"}))
        _, (new, _, actions) = self._run(items, clip={})
        self.assertEqual((new, actions), ({}, {(0, 1): "kept"}))

    def test_z_plot_is_clipped_and_keeps_z(self):
        """Z plots are clipped; old vertices keep their Z, new ones take an existing Z."""
        from shapely.geometry import Polygon

        a = Polygon([(0, 0, 5), (10, 0, 6), (10, 10, 7), (0, 10, 8)])
        b = Polygon([(8, 0, 1), (18, 0, 1), (18, 10, 1), (8, 10, 1)])
        items = [_item(0, a, "N1"), _item(1, b, "N2")]
        _, (new, _, actions) = self._run(items, cross={(0, 1): "remove_from_a"})
        self.assertEqual(actions, {(0, 1): "clipped_a"})
        clipped = new[0]
        self.assertAlmostEqual(clipped.area, 80.0)
        self.assertTrue(clipped.has_z)
        coords = list(clipped.exterior.coords)
        self.assertTrue(all(len(c) == 3 and not math.isnan(c[2]) for c in coords))
        z_by_xy = {(c[0], c[1]): c[2] for c in coords}
        self.assertEqual(z_by_xy[(0.0, 0.0)], 5)
        self.assertEqual(z_by_xy[(0.0, 10.0)], 8)

    def test_match_z(self):
        from shapely.geometry import Polygon
        from tract_geolocation_formatter.overlaps import _match_z

        z_like = Polygon([(0, 0, 3), (1, 0, 4), (1, 1, 4)])
        flat = Polygon([(0, 0), (2, 0), (2, 2)])
        nan_z = Polygon([(0, 0, 9), (2, 0, float("nan")), (2, 2, 9)])
        self.assertEqual([c[2] for c in _match_z(flat, z_like).exterior.coords], [3, 3, 3, 3])
        self.assertEqual([c[2] for c in _match_z(nan_z, z_like).exterior.coords], [9, 3, 9, 9])
        self.assertFalse(_match_z(nan_z, flat).has_z)
        self.assertTrue(_match_z(MultiPolygon(), z_like).is_empty)

    def test_input_geometries_unchanged_and_deterministic(self):
        a = box(0, 0, 10, 10)
        b = box(8, 0, 16, 8)
        c = box(7, 6, 13, 12)
        items = [_item(0, c), _item(1, b), _item(2, a)]
        before = [it["geom"].wkt for it in items]
        _, first = self._run(items)
        _, second = self._run(items)
        self.assertEqual([it["geom"].wkt for it in items], before)
        self.assertEqual(
            {k: g.wkt for k, g in first[0].items()}, {k: g.wkt for k, g in second[0].items()}
        )
        self.assertEqual(first[1:], second[1:])


if __name__ == "__main__":
    unittest.main()
