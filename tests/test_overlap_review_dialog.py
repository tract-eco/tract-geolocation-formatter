"""
Overlap review dialog (GH-12 FR-5): the three tables (contained, same NodeID,
different NodeIDs) and their "Set all to" controls.

Builds the dialog offscreen with hand-made findings (QGIS Python only; skipped
elsewhere). Nothing is exec'd: the tests set the controls and read ``results()``.
"""

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

try:
    from qgis.core import QgsApplication  # noqa: F401
    from shapely.geometry import box  # noqa: F401

    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def setUpModule():
    if QGIS_AVAILABLE:
        from _qgis_app import qgis_app

        qgis_app()


@unittest.skipUnless(QGIS_AVAILABLE, "Requires QGIS Python environment")
class OverlapReviewBulkTests(unittest.TestCase):
    def setUp(self):
        from shapely.geometry import box
        from tract_geolocation_formatter.overlaps import Finding

        g = box(0, 0, 1, 1)
        # Containment: rows 0 and 1 cross-node (default Keep), row 2 same-node
        # (default Delete contained). Plot 5 is the only plot of NodeID "D".
        # Cross-node partial: plot 6 (area 1006) vs 7 (1007), 8 (1008) vs 9 (1009).
        self.findings = [
            Finding(0, 1, "C", "containment", 0, 1, g, 10.0, 100.0, False),
            Finding(2, 3, "C", "identical", 2, 3, g, 10.0, 100.0, False),
            Finding(4, 5, "B", "containment", 4, 5, g, 10.0, 100.0, False),
            Finding(6, 7, "C", "partial", None, None, g, 20.0, 2.0, False),
            Finding(8, 9, "C", "partial", None, None, g, 90.0, 9.0, False),
            # Same-NodeID partial: plot 10 (area 1010) vs 11 (1011), 12 (1012) vs 13 (1013).
            Finding(10, 11, "B", "partial", None, None, g, 5.0, 1.0, False),
            Finding(12, 13, "B", "partial", None, None, g, 50.0, 5.0, False),
        ]
        nodes = "ABCCDDEFGHIIJJ"
        self.plots = {
            i: {"label": "Plot %d" % i, "node_id": n, "area": 1000.0 + i}
            for i, n in enumerate(nodes)
        }
        counts = {n: nodes.count(n) for n in set(nodes)}
        from tract_geolocation_formatter.overlap_review_dialog import OverlapReviewDialog

        self.dialog = OverlapReviewDialog(self.findings, self.plots, counts)

    def tearDown(self):
        from qgis.PyQt import sip

        sip.delete(self.dialog)

    def _set(self, combo, data):
        combo.setCurrentIndex(combo.findData(data))

    def _containment_actions(self):
        return self.dialog.results()[1]

    def test_containment_bulk_starts_on_dash_and_is_shown(self):
        d = self.dialog
        self.assertEqual(d.containmentBulkCombo.currentData(), "")
        self.assertFalse(d.containmentBulkCombo.isHidden())
        self.assertEqual(
            [d.containmentBulkCombo.itemData(i) for i in range(d.containmentBulkCombo.count())],
            ["", "delete_contained", "delete_container", "keep"],
        )
        # Defaults per row are unchanged by the new control.
        self.assertEqual(
            self._containment_actions(),
            {(0, 1): "keep", (2, 3): "keep", (4, 5): "delete_contained"},
        )

    def test_containment_bulk_sets_every_row(self):
        from tract_geolocation_formatter.overlap_review_dialog import (
            DELETE_CONTAINED,
            DELETE_CONTAINER,
            KEEP,
        )

        for choice in (DELETE_CONTAINED, DELETE_CONTAINER, KEEP):
            self._set(self.dialog.containmentBulkCombo, choice)
            self.assertEqual(set(self._containment_actions().values()), {choice}, choice)
            # Resets to "—" so the same choice can be applied again.
            self.assertEqual(self.dialog.containmentBulkCombo.currentIndex(), 0)

    def test_containment_bulk_rows_stay_editable(self):
        from tract_geolocation_formatter.overlap_review_dialog import DELETE_CONTAINED, KEEP

        self._set(self.dialog.containmentBulkCombo, DELETE_CONTAINED)
        self._set(self.dialog._containment_combos[1], KEEP)
        self.assertEqual(
            self._containment_actions(),
            {(0, 1): "delete_contained", (2, 3): "keep", (4, 5): "delete_contained"},
        )

    def test_containment_bulk_leaves_cross_rows_alone(self):
        from tract_geolocation_formatter.overlap_review_dialog import DELETE_CONTAINER

        before = self.dialog.results()[2]
        self._set(self.dialog.containmentBulkCombo, DELETE_CONTAINER)
        self.assertEqual(self.dialog.results()[2], before)

    def test_containment_bulk_refreshes_last_plot_warning(self):
        from tract_geolocation_formatter.overlap_review_dialog import DELETE_CONTAINED, KEEP

        # Row 0: plot 1 is the only plot of NodeID "B", so deleting it empties "B".
        # Row 2: NodeID "D" has two plots, so deleting one never warns.
        warned, safe = self.dialog.containmentTable.item(0, 0), self.dialog.containmentTable.item(2, 0)
        self.assertTrue(warned.icon().isNull())
        self._set(self.dialog.containmentBulkCombo, DELETE_CONTAINED)
        self.assertFalse(warned.icon().isNull())
        self.assertIn("B", warned.toolTip())
        self.assertTrue(safe.icon().isNull())
        self._set(self.dialog.containmentBulkCombo, KEEP)
        self.assertTrue(warned.icon().isNull())
        self.assertEqual(warned.toolTip(), "")

    def test_cross_bulk_still_works(self):
        from tract_geolocation_formatter.overlap_review_dialog import _BULK_SMALLER

        self._set(self.dialog.bulkCombo, _BULK_SMALLER)
        self.assertEqual(
            self.dialog.results()[2],
            {(6, 7): "remove_from_a", (8, 9): "remove_from_a"},
        )
        self.assertEqual(self.dialog.bulkCombo.currentIndex(), 0)

    def test_same_node_table_defaults_to_remove_from_smaller(self):
        d = self.dialog
        self.assertFalse(d.sameTable.isHidden())
        self.assertFalse(d.sameBulkCombo.isHidden())
        # Sorted by % of smaller, largest first; the smaller plot is A in both pairs.
        self.assertEqual(d.sameTable.item(0, 0).text(), "Plot 12")
        self.assertEqual(
            d.results()[0], {(10, 11): "remove_from_a", (12, 13): "remove_from_a"}
        )
        # Cross-NodeID rows still default to Keep both.
        self.assertEqual(d.results()[2], {(6, 7): "keep", (8, 9): "keep"})

    def test_same_node_bulk_sets_every_row(self):
        from tract_geolocation_formatter.overlap_review_dialog import (
            _BULK_KEEP,
            _BULK_LARGER,
            KEEP,
        )

        d = self.dialog
        self._set(d.sameBulkCombo, _BULK_LARGER)
        self.assertEqual(
            d.results()[0], {(10, 11): "remove_from_b", (12, 13): "remove_from_b"}
        )
        self.assertEqual(d.sameBulkCombo.currentIndex(), 0)
        self._set(d.sameBulkCombo, _BULK_KEEP)
        self.assertEqual(set(d.results()[0].values()), {KEEP})
        # The other tables are untouched.
        self.assertEqual(d.results()[2], {(6, 7): "keep", (8, 9): "keep"})

    def test_same_node_rows_stay_editable(self):
        from tract_geolocation_formatter.overlap_review_dialog import KEEP

        self._set(self.dialog._same_combos[0], KEEP)  # row 0 is pair (12, 13)
        self.assertEqual(
            self.dialog.results()[0], {(10, 11): "remove_from_a", (12, 13): "keep"}
        )

    def test_hidden_without_containment(self):
        from tract_geolocation_formatter.overlap_review_dialog import OverlapReviewDialog
        from qgis.PyQt import sip

        d = OverlapReviewDialog(self.findings[3:5], self.plots, {})
        try:
            self.assertTrue(d.containmentBulkCombo.isHidden())
            self.assertTrue(d.sameTable.isHidden())
            self.assertTrue(d.sameBulkCombo.isHidden())
            self.assertEqual(d.results()[0], {})
            self.assertEqual(d.results()[1], {})
        finally:
            sip.delete(d)


if __name__ == "__main__":
    unittest.main()
