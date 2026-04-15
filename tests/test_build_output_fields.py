"""
Unit tests for TractGeolocationFormatter._build_output_fields.

These tests require the QGIS Python environment (qgis.core must be importable).
Run from within QGIS Python console or a QGIS-enabled virtualenv:

    python -m pytest tests/test_build_output_fields.py -v
"""

import sys
import unittest

try:
    from qgis.core import QgsFields, QgsField
    from qgis.PyQt.QtCore import QVariant

    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _make_fields(field_defs):
    """Helper: build QgsFields from a list of (name, QVariant type) tuples."""
    fields = QgsFields()
    for name, ftype in field_defs:
        fields.append(QgsField(name, ftype))
    return fields


def _field_names(qgs_fields):
    """Helper: extract field names as a list from QgsFields."""
    return [qgs_fields.field(i).name() for i in range(qgs_fields.count())]


@unittest.skipUnless(QGIS_AVAILABLE, "Requires QGIS Python environment")
class TestBuildOutputFields(unittest.TestCase):

    def setUp(self):
        from tract_geolocation_formatter.TRACT_Geolocation_Formatter import TractGeolocationFormatter
        # Create instance without iface (we only call the helper, not plugin lifecycle)
        self.formatter = TractGeolocationFormatter.__new__(TractGeolocationFormatter)

    def test_basic_passthrough(self):
        """Original fields are carried over, TRACT fields appended at the end."""
        layer_fields = _make_fields([
            ("farm_name", QVariant.String),
            ("area_declared", QVariant.Double),
            ("region", QVariant.String),
        ])

        out_fields, rename_map = self.formatter._build_output_fields(layer_fields, set())

        names = _field_names(out_fields)
        self.assertEqual(names, [
            "farm_name", "area_declared", "region",
            "NodeID", "PlotID", "TRACTStatus", "TRACTIssue",
        ])
        self.assertEqual(rename_map, {})

    def test_excluded_fields_are_omitted(self):
        """Fields in excluded_fields are not present in output."""
        layer_fields = _make_fields([
            ("farm_id", QVariant.String),
            ("region", QVariant.String),
            ("plot_code", QVariant.String),
        ])

        out_fields, rename_map = self.formatter._build_output_fields(
            layer_fields, {"farm_id", "plot_code"}
        )

        names = _field_names(out_fields)
        self.assertEqual(names, [
            "region",
            "NodeID", "PlotID", "TRACTStatus", "TRACTIssue",
        ])
        self.assertNotIn("farm_id", names)
        self.assertNotIn("plot_code", names)
        self.assertEqual(rename_map, {})

    def test_clashing_field_gets_orig_suffix(self):
        """Input field named 'NodeID' is renamed to 'NodeID_orig'."""
        layer_fields = _make_fields([
            ("region", QVariant.String),
            ("NodeID", QVariant.String),
        ])

        out_fields, rename_map = self.formatter._build_output_fields(layer_fields, set())

        names = _field_names(out_fields)
        self.assertIn("NodeID_orig", names)
        # TRACT NodeID should still be present
        self.assertIn("NodeID", names)
        self.assertEqual(rename_map, {"NodeID": "NodeID_orig"})

    def test_tract_status_clash(self):
        """Input field named 'TRACTStatus' is renamed to 'TRACTStatus_orig'."""
        layer_fields = _make_fields([
            ("data", QVariant.String),
            ("TRACTStatus", QVariant.String),
        ])

        out_fields, rename_map = self.formatter._build_output_fields(layer_fields, set())

        names = _field_names(out_fields)
        self.assertEqual(names, [
            "data", "TRACTStatus_orig",
            "NodeID", "PlotID", "TRACTStatus", "TRACTIssue",
        ])
        self.assertEqual(rename_map, {"TRACTStatus": "TRACTStatus_orig"})

    def test_mapped_clash_is_excluded_not_renamed(self):
        """If 'NodeID' is the field mapped to NodeID (excluded), it should not appear as NodeID_orig."""
        layer_fields = _make_fields([
            ("region", QVariant.String),
            ("NodeID", QVariant.String),
        ])

        out_fields, rename_map = self.formatter._build_output_fields(
            layer_fields, {"NodeID"}
        )

        names = _field_names(out_fields)
        self.assertNotIn("NodeID_orig", names)
        # Only region + TRACT fields
        self.assertEqual(names, [
            "region",
            "NodeID", "PlotID", "TRACTStatus", "TRACTIssue",
        ])
        self.assertEqual(rename_map, {})

    def test_mapped_plotid_clash_is_excluded(self):
        """If 'PlotID' is mapped to PlotID (excluded), it should not appear as PlotID_orig."""
        layer_fields = _make_fields([
            ("region", QVariant.String),
            ("PlotID", QVariant.String),
        ])

        out_fields, rename_map = self.formatter._build_output_fields(
            layer_fields, {"PlotID"}
        )

        names = _field_names(out_fields)
        self.assertNotIn("PlotID_orig", names)
        self.assertEqual(names, [
            "region",
            "NodeID", "PlotID", "TRACTStatus", "TRACTIssue",
        ])

    def test_field_types_preserved(self):
        """Original field types are preserved in the output."""
        layer_fields = _make_fields([
            ("name", QVariant.String),
            ("area", QVariant.Double),
            ("count", QVariant.Int),
        ])

        out_fields, _ = self.formatter._build_output_fields(layer_fields, set())

        self.assertEqual(out_fields.field(0).type(), QVariant.String)  # name
        self.assertEqual(out_fields.field(1).type(), QVariant.Double)  # area
        self.assertEqual(out_fields.field(2).type(), QVariant.Int)     # count

    def test_combined_exclusion_and_clash(self):
        """Exclusion and clash handling work together correctly."""
        layer_fields = _make_fields([
            ("farm_id", QVariant.String),       # will be excluded (mapped to NodeID)
            ("NodeID", QVariant.String),         # clashes → NodeID_orig
            ("plot_code", QVariant.String),      # will be excluded (mapped to PlotID)
            ("TRACTIssue", QVariant.String),     # clashes → TRACTIssue_orig
            ("region", QVariant.String),         # normal passthrough
        ])

        out_fields, rename_map = self.formatter._build_output_fields(
            layer_fields, {"farm_id", "plot_code"}
        )

        names = _field_names(out_fields)
        self.assertEqual(names, [
            "NodeID_orig", "TRACTIssue_orig", "region",
            "NodeID", "PlotID", "TRACTStatus", "TRACTIssue",
        ])
        self.assertEqual(rename_map, {
            "NodeID": "NodeID_orig",
            "TRACTIssue": "TRACTIssue_orig",
        })

    def test_empty_layer_fields(self):
        """Layer with no fields produces only TRACT fields."""
        layer_fields = QgsFields()

        out_fields, rename_map = self.formatter._build_output_fields(layer_fields, set())

        names = _field_names(out_fields)
        self.assertEqual(names, ["NodeID", "PlotID", "TRACTStatus", "TRACTIssue"])
        self.assertEqual(rename_map, {})


if __name__ == "__main__":
    unittest.main()
