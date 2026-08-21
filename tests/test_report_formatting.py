"""
Unit tests for the pop-up report formatting helpers.

Tests the pure module-level helpers in TRACT_Geolocation_Formatter that lay out
the report shown in the summary dialog:
- _plural
- _format_aligned_rows
- _ReportBuilder

The report is built once as a structured document and rendered two ways: Qt
rich text for the dialog (bold headings, columns aligned by table cells) and
plain text for logging (columns aligned by padding spaces).

Importing the main module requires qgis.PyQt to be importable; tests skip
gracefully if it is not (same pattern as test_master_data_writer.py).

Run:
    python -m unittest tests.test_report_formatting -v
"""

import unittest

try:
    from tract_geolocation_formatter.TRACT_Geolocation_Formatter import (
        _format_aligned_rows,
        _plural,
        _ReportBuilder,
    )

    HELPERS_AVAILABLE = True
except ImportError:
    HELPERS_AVAILABLE = False


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires qgis.PyQt to import the plugin module")
class TestPlural(unittest.TestCase):
    def test_singular(self):
        self.assertEqual(_plural(1, "feature"), "1 feature")

    def test_plural_default_s(self):
        self.assertEqual(_plural(4, "feature"), "4 features")

    def test_zero_is_plural(self):
        self.assertEqual(_plural(0, "feature"), "0 features")

    def test_explicit_plural_form(self):
        self.assertEqual(_plural(2, "polygon part", "polygon parts"), "2 polygon parts")
        self.assertEqual(_plural(1, "polygon part", "polygon parts"), "1 polygon part")


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires qgis.PyQt to import the plugin module")
class TestFormatAlignedRows(unittest.TestCase):
    """_format_aligned_rows backs the plain-text rendering of the report."""

    def test_values_align_to_longest_label(self):
        rows = [("Output", "/tmp/a.geojson"), ("Validation report", "/tmp/a.csv")]
        self.assertEqual(
            _format_aligned_rows(rows),
            [
                "  Output             /tmp/a.geojson",
                "  Validation report  /tmp/a.csv",
            ],
        )

    def test_empty_value_yields_label_only_no_trailing_space(self):
        rows = [("Feature 6", ""), ("Feature 10", "")]
        self.assertEqual(_format_aligned_rows(rows), ["  Feature 6", "  Feature 10"])

    def test_empty_label_is_a_continuation_row(self):
        """A blank label lets several values sit under one heading, still aligned."""
        rows = [("Split output", "/tmp/a-1.geojson"), ("", "/tmp/a-2.geojson")]
        self.assertEqual(
            _format_aligned_rows(rows),
            [
                "  Split output  /tmp/a-1.geojson",
                "                /tmp/a-2.geojson",
            ],
        )

    def test_indent_and_gap_are_configurable(self):
        rows = [("Feature 5", "0.0003 ha")]
        self.assertEqual(
            _format_aligned_rows(rows, indent="    ", gap=4),
            ["    Feature 5    0.0003 ha"],
        )

    def test_empty_input(self):
        self.assertEqual(_format_aligned_rows([]), [])

    def test_single_row_has_exactly_one_gap(self):
        self.assertEqual(_format_aligned_rows([("A", "B")], gap=2), ["  A  B"])


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires qgis.PyQt to import the plugin module")
class TestReportBuilderHtml(unittest.TestCase):
    """The dialog rendering — must escape user data and not force fonts/colours."""

    def test_section_is_bold(self):
        b = _ReportBuilder()
        b.section("SUMMARY")
        self.assertIn("<b>SUMMARY</b>", b.to_html())

    def test_rows_render_as_a_table(self):
        b = _ReportBuilder()
        b.rows([("Output", "/tmp/a.geojson")])
        html = b.to_html()
        self.assertIn("<table", html)
        self.assertIn("<td", html)
        self.assertIn("/tmp/a.geojson", html)

    def test_empty_rows_emit_nothing(self):
        b = _ReportBuilder()
        b.rows([])
        self.assertEqual(b.to_html(), "")
        self.assertEqual(b.to_plain_text(), "")

    def test_indent_level_scales_left_margin(self):
        b = _ReportBuilder()
        b.rows([("a", "b")], level=2)
        self.assertIn("margin-left:36px", b.to_html())

    def test_user_data_is_html_escaped(self):
        """A PlotID or path containing markup must never reach the widget as markup."""
        b = _ReportBuilder()
        b.rows([("Feature 1 (PlotID = <b>x</b>)", "/tmp/a & b.geojson")])
        html = b.to_html()
        self.assertNotIn("<b>x</b>", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertIn("&amp;", html)

    def test_escaping_applies_to_every_element_kind(self):
        b = _ReportBuilder()
        b.title("<t>")
        b.section("<s>")
        b.subsection("<sub>")
        b.bullet("<bul>")
        b.note("<n>")
        html = b.to_html()
        for raw in ("<t>", "<s>", "<sub>", "<bul>", "<n>"):
            self.assertNotIn(raw, html)
            self.assertIn(f"&lt;{raw[1:-1]}&gt;", html)

    def test_no_font_or_colour_is_forced(self):
        """Everything must inherit the widget font and the active QGIS theme."""
        b = _ReportBuilder()
        b.title("t")
        b.section("s")
        b.rows([("a", "b")])
        b.bullet("c")
        html = b.to_html()
        self.assertNotIn("font-family", html)
        self.assertNotIn("font-size", html)
        self.assertNotIn("color:", html)

    def test_bullet_uses_a_dash_not_an_exclamation_mark(self):
        b = _ReportBuilder()
        b.bullet("1 feature skipped")
        self.assertNotIn("!", b.to_html())
        self.assertIn("&#8211;", b.to_html())
        self.assertTrue(b.to_plain_text().strip().startswith("- "))


@unittest.skipUnless(HELPERS_AVAILABLE, "Requires qgis.PyQt to import the plugin module")
class TestReportBuilderPlainText(unittest.TestCase):
    """The logging rendering — same document, space-aligned."""

    def test_sections_are_preceded_by_a_blank_line(self):
        b = _ReportBuilder()
        b.title("Export finished.")
        b.section("SUMMARY")
        self.assertEqual(b.to_plain_text(), "Export finished.\n\nSUMMARY")

    def test_rows_are_indented_and_aligned(self):
        b = _ReportBuilder()
        b.rows([("Input features", "9"), ("Written", "8")])
        self.assertEqual(
            b.to_plain_text(),
            "  Input features    9\n  Written           8",
        )

    def test_bullet_run_is_set_off_from_what_precedes_it(self):
        b = _ReportBuilder()
        b.rows([("Skipped", "1")])
        b.bullet("first")
        b.bullet("second")
        self.assertEqual(
            b.to_plain_text().split("\n"),
            ["  Skipped    1", "", "  - first", "  - second"],
        )

    def test_nested_level_indents_further(self):
        b = _ReportBuilder()
        b.subsection("Interior holes (1)", level=1)
        b.rows([("Feature 6", "")], level=2)
        self.assertEqual(
            b.to_plain_text(),
            "  Interior holes (1)\n    Feature 6",
        )
