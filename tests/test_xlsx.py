"""
Unit tests for the stdlib-only XLSX reader/writer (tract_geolocation_formatter.xlsx).

This module replaced the vendored openpyxl, so these tests carry the weight
that openpyxl's own test suite used to. They need no third-party packages and
no QGIS — the module is pure standard library.

Run:
    python -m pytest tests/test_xlsx.py -v
"""

import hashlib
import os
import shutil
import tempfile
import unittest
import zipfile

from tract_geolocation_formatter.xlsx import (
    read_cells,
    read_column,
    sheet_names,
    write_cells,
)

_TEMPLATES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tract_geolocation_formatter",
    "templates",
)
_FARMS = os.path.join(_TEMPLATES, "farms_master_data_template.xlsx")
_FG = os.path.join(_TEMPLATES, "farmer_group_master_data_template.xlsx")

_EXPECTED_SHEETS = [
    "0. Introduction",
    "1. ReadMe",
    "2.Farms_Template",
    ">>>",
    "3.Farms_Sample data",
    "4. Country_List",
    "Config",
]


def _sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class _TempOut(unittest.TestCase):
    """Base class giving each test a scratch output path."""

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.out = os.path.join(self._dir, "out.xlsx")

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)


class TestSheetNames(unittest.TestCase):
    def test_farms_sheet_names_in_tab_order(self):
        self.assertEqual(sheet_names(_FARMS), _EXPECTED_SHEETS)

    def test_bare_gt_in_sheet_name_is_read(self):
        """The '>>>' sheet name contains a literal '>', which is legal XML.

        A naive [^>]* attribute scan truncates that tag and drops the sheet.
        """
        self.assertIn(">>>", sheet_names(_FARMS))
        self.assertIn(">>>", sheet_names(_FG))


class TestReadColumn(unittest.TestCase):
    def test_country_list(self):
        countries = read_column(_FARMS, "4. Country_List", "B", first_row=2)
        self.assertEqual(len(countries), 250)
        self.assertEqual(countries[0], "Afghanistan")
        self.assertEqual(countries[-1], "Zimbabwe")

    def test_identical_across_templates(self):
        self.assertEqual(
            read_column(_FARMS, "4. Country_List", "B", first_row=2),
            read_column(_FG, "4. Country_List", "B", first_row=2),
        )

    def test_non_ascii_preserved(self):
        countries = read_column(_FARMS, "4. Country_List", "B", first_row=2)
        self.assertIn("Côte d'Ivoire", countries)

    def test_first_row_skips_header(self):
        with_header = read_column(_FARMS, "4. Country_List", "B", first_row=1)
        without = read_column(_FARMS, "4. Country_List", "B", first_row=2)
        self.assertEqual(len(with_header) - len(without), 1)

    def test_missing_sheet_raises_key_error(self):
        with self.assertRaises(KeyError):
            read_column(_FARMS, "No Such Sheet", "A")


class TestReadCells(unittest.TestCase):
    def test_header_row(self):
        self.assertEqual(
            read_cells(_FARMS, "2.Farms_Template", ("B2", "E2", "I2")),
            {"B2": "Farm Name", "E2": "Country", "I2": "Node_ID"},
        )

    def test_blank_cell_is_empty_string(self):
        self.assertEqual(read_cells(_FARMS, "2.Farms_Template", ("B3",)), {"B3": ""})

    def test_absent_cell_is_empty_string(self):
        """Column J no longer exists in the template at all."""
        self.assertEqual(read_cells(_FARMS, "2.Farms_Template", ("J2",)), {"J2": ""})

    def test_numeric_cell_read_as_text(self):
        # Sample-data sheet row 3 carries numeric latitude/longitude.
        value = read_cells(_FARMS, "3.Farms_Sample data", ("C3",))["C3"]
        self.assertTrue(value.startswith("0.765"), value)


class TestWriteCells(_TempOut):
    def test_writes_into_existing_cells(self):
        write_cells(_FARMS, self.out, "2.Farms_Template",
                    {(3, "B"): "N1", (3, "E"): "Ghana", (3, "I"): "N1"})
        self.assertEqual(
            read_cells(self.out, "2.Farms_Template", ("B3", "E3", "I3")),
            {"B3": "N1", "E3": "Ghana", "I3": "N1"},
        )

    def test_template_is_not_modified(self):
        before = _sha256(_FARMS)
        write_cells(_FARMS, self.out, "2.Farms_Template", {(3, "B"): "N1"})
        self.assertEqual(_sha256(_FARMS), before)

    def test_all_sheets_survive(self):
        write_cells(_FARMS, self.out, "2.Farms_Template", {(3, "B"): "N1"})
        self.assertEqual(sheet_names(self.out), _EXPECTED_SHEETS)

    def test_headers_and_other_sheets_untouched(self):
        write_cells(_FARMS, self.out, "2.Farms_Template", {(3, "B"): "N1"})
        self.assertEqual(
            read_cells(self.out, "2.Farms_Template", ("B2", "I2")),
            {"B2": "Farm Name", "I2": "Node_ID"},
        )
        self.assertEqual(
            read_column(self.out, "4. Country_List", "B", first_row=2)[:1],
            ["Afghanistan"],
        )

    def test_writes_cells_absent_from_the_template_row(self):
        """Farms row 7 has only C/D/E cells — B and I must be inserted."""
        write_cells(_FARMS, self.out, "2.Farms_Template",
                    {(7, "B"): "N5", (7, "E"): "Ghana", (7, "I"): "N5"})
        self.assertEqual(
            read_cells(self.out, "2.Farms_Template", ("B7", "E7", "I7")),
            {"B7": "N5", "E7": "Ghana", "I7": "N5"},
        )

    def test_creates_rows_beyond_the_template(self):
        """The farmer-groups sheet only has rows 1-6; row 12 must be created."""
        values = {}
        for index in range(10):
            row = 3 + index
            values[(row, "A")] = "G%d" % (index + 1)
            values[(row, "C")] = "Ghana"
            values[(row, "G")] = "G%d" % (index + 1)
        write_cells(_FG, self.out, "2. Farmer_Groups Template", values)
        self.assertEqual(
            read_cells(self.out, "2. Farmer_Groups Template", ("A7", "G7", "A12", "G12")),
            {"A7": "G5", "G7": "G5", "A12": "G10", "G12": "G10"},
        )

    def test_created_rows_widen_the_dimension(self):
        write_cells(_FG, self.out, "2. Farmer_Groups Template", {(12, "A"): "G10"})
        with zipfile.ZipFile(self.out) as archive:
            sheet = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
        self.assertIn('<dimension ref="A1:G12"/>', sheet)

    def test_xml_metacharacters_are_escaped(self):
        write_cells(_FARMS, self.out, "2.Farms_Template",
                    {(3, "B"): 'A & B <tag> "q"', (3, "I"): "x</t><t>inject"})
        self.assertEqual(
            read_cells(self.out, "2.Farms_Template", ("B3", "I3")),
            {"B3": 'A & B <tag> "q"', "I3": "x</t><t>inject"},
        )

    def test_leading_trailing_space_preserved(self):
        write_cells(_FARMS, self.out, "2.Farms_Template", {(3, "B"): "  padded  "})
        self.assertEqual(read_cells(self.out, "2.Farms_Template", ("B3",))["B3"], "  padded  ")

    def test_empty_and_none_values_are_skipped(self):
        write_cells(_FARMS, self.out, "2.Farms_Template",
                    {(3, "B"): "N1", (3, "E"): "", (3, "I"): None})
        self.assertEqual(
            read_cells(self.out, "2.Farms_Template", ("B3", "E3", "I3")),
            {"B3": "N1", "E3": "", "I3": ""},
        )

    def test_no_values_copies_template_verbatim(self):
        write_cells(_FARMS, self.out, "2.Farms_Template", {})
        self.assertEqual(_sha256(self.out), _sha256(_FARMS))

    def test_every_zip_entry_is_preserved(self):
        write_cells(_FARMS, self.out, "2.Farms_Template", {(3, "B"): "N1"})
        with zipfile.ZipFile(_FARMS) as src, zipfile.ZipFile(self.out) as dst:
            self.assertEqual(set(src.namelist()), set(dst.namelist()))

    def test_country_dropdown_survives(self):
        """The extLst data validation openpyxl silently dropped."""
        write_cells(_FARMS, self.out, "2.Farms_Template", {(3, "B"): "N1"})
        with zipfile.ZipFile(self.out) as archive:
            sheet = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
        self.assertIn("x14:dataValidation", sheet)
        self.assertIn("Country_List", sheet)

    def test_missing_sheet_raises_key_error(self):
        with self.assertRaises(KeyError):
            write_cells(_FARMS, self.out, "No Such Sheet", {(3, "A"): "x"})


if __name__ == "__main__":
    unittest.main()
