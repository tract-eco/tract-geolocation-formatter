"""
Unit tests for TractGeolocationFormatter._build_expression_value.

Requires QGIS Python environment (qgis.core must be importable).
"""

import unittest

try:
    from qgis.core import QgsFields, QgsField, QgsFeature, QgsVectorLayer
    from qgis.PyQt.QtCore import QVariant

    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _make_feature(field_defs, values):
    """Helper: create a QgsFeature with given fields and values.

    field_defs: list of (name, QVariant type)
    values: list of values matching field_defs order
    """
    fields = QgsFields()
    for name, ftype in field_defs:
        fields.append(QgsField(name, ftype))
    feat = QgsFeature(fields)
    feat.setAttributes(values)
    return feat, fields


def _make_layer_and_feature(field_defs, values):
    """Helper: create a memory layer and a feature for testing."""
    type_str = "Polygon?crs=epsg:4326"
    for name, ftype in field_defs:
        if ftype == QVariant.String:
            type_str += f"&field={name}:string"
        elif ftype == QVariant.Int:
            type_str += f"&field={name}:integer"
        elif ftype == QVariant.Double:
            type_str += f"&field={name}:double"

    layer = QgsVectorLayer(type_str, "test", "memory")
    feat = QgsFeature(layer.fields())
    feat.setAttributes(values)
    return layer, feat


@unittest.skipUnless(QGIS_AVAILABLE, "Requires QGIS Python environment")
class TestBuildExpressionValue(unittest.TestCase):

    def setUp(self):
        from tract_geolocation_formatter.TRACT_Geolocation_Formatter import TractGeolocationFormatter
        self.formatter = TractGeolocationFormatter.__new__(TractGeolocationFormatter)

    def test_all_parts(self):
        """All parts filled: prefix + field1 + field2 + suffix."""
        layer, feat = _make_layer_and_feature(
            [("region", QVariant.String), ("farm_id", QVariant.String)],
            ["MATO_GROSSO", "12345"],
        )
        result = self.formatter._build_expression_value(
            feat, layer, "BR", "region", "farm_id", "", "_"
        )
        self.assertEqual(result, "BR_MATO_GROSSO_12345")

    def test_all_parts_with_suffix(self):
        """All parts including suffix."""
        layer, feat = _make_layer_and_feature(
            [("region", QVariant.String), ("farm_id", QVariant.String)],
            ["MATO", "123"],
        )
        result = self.formatter._build_expression_value(
            feat, layer, "BR", "region", "farm_id", "end", "_"
        )
        self.assertEqual(result, "BR_MATO_123_end")

    def test_prefix_and_field1_only(self):
        """Prefix + field1, no field2, no suffix."""
        layer, feat = _make_layer_and_feature(
            [("code", QVariant.String)],
            ["ABC123"],
        )
        result = self.formatter._build_expression_value(
            feat, layer, "ID", "code", "", "", "_"
        )
        self.assertEqual(result, "ID_ABC123")

    def test_field1_and_suffix_only(self):
        """No prefix, field1 + suffix."""
        layer, feat = _make_layer_and_feature(
            [("code", QVariant.String)],
            ["ABC"],
        )
        result = self.formatter._build_expression_value(
            feat, layer, "", "code", "", "end", "-"
        )
        self.assertEqual(result, "ABC-end")

    def test_null_field_value_omitted(self):
        """Null field1 value is omitted, no double separator."""
        layer, feat = _make_layer_and_feature(
            [("region", QVariant.String)],
            [None],
        )
        result = self.formatter._build_expression_value(
            feat, layer, "X", "region", "", "Y", "_"
        )
        self.assertEqual(result, "X_Y")

    def test_empty_string_field_omitted(self):
        """Empty string field value is omitted."""
        layer, feat = _make_layer_and_feature(
            [("region", QVariant.String)],
            [""],
        )
        result = self.formatter._build_expression_value(
            feat, layer, "X", "region", "", "Y", "_"
        )
        self.assertEqual(result, "X_Y")

    def test_field1_only_no_prefix_no_suffix(self):
        """Just a single field, nothing else."""
        layer, feat = _make_layer_and_feature(
            [("name", QVariant.String)],
            ["hello"],
        )
        result = self.formatter._build_expression_value(
            feat, layer, "", "name", "", "", "_"
        )
        self.assertEqual(result, "hello")

    def test_integer_field_converted_to_string(self):
        """Integer field values are converted to string."""
        layer, feat = _make_layer_and_feature(
            [("plot_num", QVariant.Int)],
            [42],
        )
        result = self.formatter._build_expression_value(
            feat, layer, "P", "plot_num", "", "", "_"
        )
        self.assertEqual(result, "P_42")

    def test_custom_separator(self):
        """Separator other than underscore."""
        layer, feat = _make_layer_and_feature(
            [("a", QVariant.String), ("b", QVariant.String)],
            ["X", "Y"],
        )
        result = self.formatter._build_expression_value(
            feat, layer, "pre", "a", "b", "suf", "-"
        )
        self.assertEqual(result, "pre-X-Y-suf")


if __name__ == "__main__":
    unittest.main()
