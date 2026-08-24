"""
Unit tests for the GH-6 Master Data XLSX writer helpers.

Tests the pure-Python module-level helpers in TRACT_Geolocation_Formatter:
- _MASTER_DATA_MAPPING (constant)
- _master_data_output_path
- _read_country_list_from_template
- _write_master_data_xlsx

Output is verified with the plugin's own stdlib XLSX reader
(tract_geolocation_formatter.xlsx), which replaced the vendored openpyxl — so
these tests need no third-party packages. The reader itself is covered
independently by tests/test_xlsx.py.

Importing the main module still requires qgis.PyQt; tests skip gracefully if it
is unavailable (same pattern as test_self_intersection_coordinates.py).
"""

import hashlib
import os
import shutil
import tempfile
import unittest

from tract_geolocation_formatter.xlsx import read_cells, read_column, sheet_names

try:
    from tract_geolocation_formatter.TRACT_Geolocation_Formatter import (
        _MASTER_DATA_MAPPING,
        _master_data_output_path,
        _read_country_list_from_template,
        _write_master_data_xlsx,
    )

    HELPERS_AVAILABLE = True
except ImportError:
    HELPERS_AVAILABLE = False


_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tract_geolocation_formatter",
)
_TEMPLATES_DIR = os.path.join(_PLUGIN_DIR, "templates")
_FARMS_TEMPLATE = os.path.join(_TEMPLATES_DIR, "farms_master_data_template.xlsx")
_FARMER_GROUPS_TEMPLATE = os.path.join(_TEMPLATES_DIR, "farmer_group_master_data_template.xlsx")

_EXPECTED_FARMS_SHEETS = [
    "0. Introduction",
    "1. ReadMe",
    "2.Farms_Template",
    ">>>",
    "3.Farms_Sample data",
    "4. Country_List",
    "Config",
]


def _sha256(path):
    """Compute SHA-256 of a file for integrity comparison."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires qgis.PyQt to import the plugin module")
class TestMasterDataOutputPath(unittest.TestCase):
    """Pure string manipulation — no filesystem touch."""

    def test_geojson_extension(self):
        self.assertEqual(
            _master_data_output_path("/tmp/mali_nodes.geojson", "farms"),
            "/tmp/mali_nodes_master_data_farms.xlsx",
        )

    def test_json_extension(self):
        self.assertEqual(
            _master_data_output_path("/tmp/mali_nodes.json", "farmer_groups"),
            "/tmp/mali_nodes_master_data_farmer_groups.xlsx",
        )

    def test_path_with_no_extension(self):
        # os.path.splitext returns (path, "") for a path without an extension.
        self.assertEqual(
            _master_data_output_path("/tmp/data", "farms"),
            "/tmp/data_master_data_farms.xlsx",
        )


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires qgis.PyQt to import the plugin module")
class TestMasterDataCellMapping(unittest.TestCase):
    """Confirm _MASTER_DATA_MAPPING matches the actual template column layout."""

    def test_farms_mapping_matches_template(self):
        mapping = _MASTER_DATA_MAPPING["farms"]
        self.assertEqual(mapping["sheet_name"], "2.Farms_Template")
        self.assertEqual(mapping["name_col"], "B")
        self.assertEqual(mapping["country_col"], "E")
        self.assertEqual(mapping["node_id_col"], "I")

        self.assertIn(mapping["sheet_name"], sheet_names(_FARMS_TEMPLATE))
        headers = read_cells(
            _FARMS_TEMPLATE,
            mapping["sheet_name"],
            ("%s2" % mapping["name_col"],
             "%s2" % mapping["country_col"],
             "%s2" % mapping["node_id_col"]),
        )
        self.assertEqual(headers["%s2" % mapping["name_col"]], "Farm Name")
        self.assertEqual(headers["%s2" % mapping["country_col"]], "Country")
        self.assertEqual(headers["%s2" % mapping["node_id_col"]], "Node_ID")

    def test_farms_template_has_no_geojson_column(self):
        """TRACT dropped the GeoJson column — the bundled template must match."""
        for sheet_name in ("2.Farms_Template", "3.Farms_Sample data"):
            cells = read_cells(_FARMS_TEMPLATE, sheet_name, ("I2", "J2"))
            self.assertEqual(cells["I2"], "Node_ID", sheet_name)
            self.assertEqual(cells["J2"], "", sheet_name)

    def test_farms_entry_sheet_ships_empty(self):
        """No leftover sample/test data in the data-entry sheet's first row."""
        row3 = read_cells(
            _FARMS_TEMPLATE, "2.Farms_Template",
            tuple("%s3" % c for c in "ABCDEFGHI"),
        )
        self.assertEqual({k: v for k, v in row3.items() if v}, {})

    def test_farmer_groups_mapping_matches_template(self):
        mapping = _MASTER_DATA_MAPPING["farmer_groups"]
        self.assertEqual(mapping["sheet_name"], "2. Farmer_Groups Template")
        self.assertEqual(mapping["name_col"], "A")
        self.assertEqual(mapping["country_col"], "C")
        self.assertEqual(mapping["node_id_col"], "G")

        self.assertIn(mapping["sheet_name"], sheet_names(_FARMER_GROUPS_TEMPLATE))
        headers = read_cells(
            _FARMER_GROUPS_TEMPLATE,
            mapping["sheet_name"],
            ("%s2" % mapping["name_col"],
             "%s2" % mapping["country_col"],
             "%s2" % mapping["node_id_col"]),
        )
        self.assertEqual(headers["%s2" % mapping["name_col"]], "Farmer_Group_Name")
        self.assertEqual(headers["%s2" % mapping["country_col"]], "Country")
        self.assertEqual(headers["%s2" % mapping["node_id_col"]], "Node_ID")


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires qgis.PyQt to import the plugin module")
class TestReadCountryList(unittest.TestCase):
    """AC-5 unit-level: 250 countries in TRACT order, first Afghanistan, last Zimbabwe."""

    def test_read_country_list_from_farms_template(self):
        countries = _read_country_list_from_template(_FARMS_TEMPLATE)
        self.assertEqual(len(countries), 250)
        self.assertEqual(countries[0], "Afghanistan")
        self.assertEqual(countries[-1], "Zimbabwe")

    def test_read_country_list_identical_across_templates(self):
        """Both bundled templates carry the same country list."""
        farms_list = _read_country_list_from_template(_FARMS_TEMPLATE)
        fg_list = _read_country_list_from_template(_FARMER_GROUPS_TEMPLATE)
        self.assertEqual(farms_list, fg_list)


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires qgis.PyQt to import the plugin module")
class TestWriteMasterDataXlsx(unittest.TestCase):
    """Integration tests for the writer — read the produced file back."""

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self._dir, "out.xlsx")

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def _write(self, master_data_type, country, unique_node_ids):
        template = _FARMS_TEMPLATE if master_data_type == "farms" else _FARMER_GROUPS_TEMPLATE
        _write_master_data_xlsx(
            template, self.output_path, master_data_type, country, unique_node_ids
        )
        return _MASTER_DATA_MAPPING[master_data_type]["sheet_name"]

    def test_write_farms_single_node(self):
        """AC-2: single unique NodeID → one data row at row 3 in B/E/I."""
        sheet = self._write("farms", "Brazil", ["NODE_001"])
        cells = read_cells(self.output_path, sheet,
                           ("B3", "E3", "I3", "B4", "E4", "I4"))
        self.assertEqual((cells["B3"], cells["E3"], cells["I3"]),
                         ("NODE_001", "Brazil", "NODE_001"))
        # Row 4 entirely empty (only 1 row written)
        self.assertEqual((cells["B4"], cells["E4"], cells["I4"]), ("", "", ""))

    def test_write_farms_multiple_nodes_order_preserved(self):
        """AC-6: caller passes an already-deduped list; writer preserves order."""
        sheet = self._write("farms", "Colombia", ["A", "B", "C"])
        cells = read_cells(self.output_path, sheet,
                           ("B3", "B4", "B5", "B6", "E3", "E4", "E5", "I3", "I4", "I5"))
        self.assertEqual([cells["B3"], cells["B4"], cells["B5"]], ["A", "B", "C"])
        # Country same on all 3 rows; Node_ID equals Farm Name on every row
        for row in (3, 4, 5):
            self.assertEqual(cells["E%d" % row], "Colombia")
            self.assertEqual(cells["I%d" % row], cells["B%d" % row])
        self.assertEqual(cells["B6"], "")

    def test_write_farmer_groups_cell_positions(self):
        """AC-3: farmer-groups uses columns A/C/G, not B/E/I."""
        sheet = self._write("farmer_groups", "Côte d'Ivoire", ["GRP_1", "GRP_2"])
        cells = read_cells(self.output_path, sheet,
                           ("A3", "C3", "G3", "A4", "C4", "G4", "B3", "E3", "I3"))
        self.assertEqual((cells["A3"], cells["C3"], cells["G3"]),
                         ("GRP_1", "Côte d'Ivoire", "GRP_1"))
        self.assertEqual((cells["A4"], cells["C4"], cells["G4"]),
                         ("GRP_2", "Côte d'Ivoire", "GRP_2"))
        # B/E/I are NOT the farmer-groups columns — must stay empty
        self.assertEqual((cells["B3"], cells["E3"], cells["I3"]), ("", "", ""))

    def test_write_more_rows_than_the_template_has(self):
        """The farmer-groups sheet only ships rows 1-6; extra rows are created."""
        ids = ["G%d" % n for n in range(1, 11)]
        sheet = self._write("farmer_groups", "Ghana", ids)
        cells = read_cells(self.output_path, sheet, ("A7", "G7", "A12", "C12", "G12"))
        self.assertEqual((cells["A7"], cells["G7"]), ("G5", "G5"))
        self.assertEqual((cells["A12"], cells["C12"], cells["G12"]),
                         ("G10", "Ghana", "G10"))

    def test_write_preserves_all_sheets(self):
        """AC-4: all 7 sheets present in the output, names byte-identical."""
        self._write("farms", "Brazil", ["NODE"])
        self.assertEqual(sheet_names(self.output_path), _EXPECTED_FARMS_SHEETS)

    def test_write_preserves_country_list(self):
        """The country list must survive, since the dialog reads it back."""
        self._write("farms", "Brazil", ["NODE"])
        countries = read_column(self.output_path, "4. Country_List", "B", first_row=2)
        self.assertEqual(len(countries), 250)
        self.assertEqual(countries[0], "Afghanistan")

    def test_write_does_not_modify_template_on_disk(self):
        """The bundled template file is byte-identical before and after a write."""
        before = _sha256(_FARMS_TEMPLATE)
        self._write("farms", "Brazil", ["NODE_X"])
        self.assertEqual(_sha256(_FARMS_TEMPLATE), before)

    def test_unknown_master_data_type_raises(self):
        with self.assertRaises(KeyError):
            _write_master_data_xlsx(
                _FARMS_TEMPLATE, self.output_path, "not_a_type", "Brazil", ["N"]
            )


if __name__ == "__main__":
    unittest.main()
