"""
Dialog controls and settings for the land cover check (SPEC-landcover-overlap, Task 3).

Loads the real .ui offscreen (QGIS Python only; skipped elsewhere). Settings go to a
throw-away INI folder (see _qgis_app.py), never to the user's QGIS settings.
"""

import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "fixtures"))

try:
    from osgeo import gdal  # noqa: F401
    from qgis.core import QgsProject  # noqa: F401

    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def setUpModule():
    if QGIS_AVAILABLE:
        from _qgis_app import qgis_app

        qgis_app()


@unittest.skipUnless(QGIS_AVAILABLE, "Requires QGIS Python environment")
class LandcoverDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from make_landcover_fixture import make_fixture
        from qgis.core import (QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer,
                               QgsVectorLayer)
        from qgis.PyQt.QtGui import QColor

        cls.tmp = tempfile.mkdtemp(prefix="tract_landcover_dialog_")
        fx = make_fixture(cls.tmp)
        cls.paletted = QgsRasterLayer(fx["main"], "classified", "gdal")
        classes = [
            QgsPalettedRasterRenderer.Class(v, QColor(c), label)
            for v, c, label in [(10, "green", "Tree"), (50, "red", "Built-up"), (80, "blue", "Water")]
        ]
        cls.paletted.setRenderer(QgsPalettedRasterRenderer(cls.paletted.dataProvider(), 1, classes))
        cls.three_band = QgsRasterLayer(fx["three_band"], "three bands", "gdal")
        cls.vector = QgsVectorLayer("Polygon?crs=EPSG:4326", "plots", "memory")
        QgsProject.instance().addMapLayers([cls.paletted, cls.three_band, cls.vector])

    @classmethod
    def tearDownClass(cls):
        from qgis.core import QgsProject

        QgsProject.instance().removeAllMapLayers()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from qgis.core import QgsSettings

        from tract_geolocation_formatter.TRACT_Geolocation_Formatter import (
            LANDCOVER_SETTINGS_PREFIX,
            TractGeolocationFormatter,
        )
        from tract_geolocation_formatter.TRACT_Geolocation_Formatter_dialog import (
            TractGeolocationFormatterDialog,
        )

        QgsSettings().remove(LANDCOVER_SETTINGS_PREFIX.rstrip("/"))
        self.plugin = TractGeolocationFormatter.__new__(TractGeolocationFormatter)
        self.plugin.dlg = TractGeolocationFormatterDialog()
        self.plugin._connect_landcover_signals()
        self.plugin._load_landcover_settings()
        self.d = self.plugin.dlg

    def tearDown(self):
        # Destroy the dialog now: deleteLater() needs an event loop, and many live
        # dialogs listening to the project crash QGIS 3.38 at removeAllMapLayers().
        from qgis.PyQt import sip

        sip.delete(self.d)
        self.plugin.dlg = None

    def _select(self, combo, data):
        combo.setCurrentIndex(combo.findData(data))

    def test_defaults_unticked_worldcover_and_disabled(self):
        for box, source in ((self.d.landcoverWaterCheckBox, self.d.landcoverWaterSourceCombo),
                            (self.d.landcoverBuiltUpCheckBox, self.d.landcoverBuiltUpSourceCombo)):
            self.assertFalse(box.isChecked())
            self.assertEqual(source.currentData(), "worldcover")
            self.assertEqual([source.itemData(i) for i in range(source.count())], ["worldcover", "project"])
            self.assertEqual([source.itemText(i) for i in range(source.count())],
                             ["ESA WorldCover 2021", "User layer"])
            self.assertFalse(source.isEnabled())
        self.assertFalse(self.d.landcoverWaterLayerCombo.isEnabled())
        self.assertIn("separate CSV", self.d.landcoverGroupBox.toolTip())
        self.assertIn("ESA's servers", self.d.landcoverWaterSourceCombo.toolTip())
        self.assertFalse(self.plugin._landcover_config_from_dialog().enabled)

    def test_ac39_enable_logic_per_row(self):
        """AC-39: Source follows the row checkbox; layer/band/value need Source = project."""
        d = self.d
        d.landcoverWaterCheckBox.setChecked(True)
        self.assertTrue(d.landcoverWaterSourceCombo.isEnabled())
        self.assertFalse(d.landcoverWaterLayerCombo.isEnabled())
        self._select(d.landcoverWaterSourceCombo, "project")
        for w in (d.landcoverWaterLayerCombo, d.landcoverWaterBandCombo, d.landcoverWaterValueCombo):
            self.assertTrue(w.isEnabled())
        # The other row is independent.
        self.assertFalse(d.landcoverBuiltUpSourceCombo.isEnabled())
        self.assertFalse(d.landcoverBuiltUpLayerCombo.isEnabled())
        d.landcoverWaterCheckBox.setChecked(False)
        self.assertFalse(d.landcoverWaterSourceCombo.isEnabled())
        self.assertFalse(d.landcoverWaterLayerCombo.isEnabled())

    def test_layer_combo_lists_rasters_only_with_empty_entry(self):
        combo = self.d.landcoverWaterLayerCombo
        names = [combo.itemText(i) for i in range(combo.count())]
        self.assertIn("classified", names)
        self.assertIn("three bands", names)
        self.assertNotIn("plots", names)
        self.assertTrue(combo.allowEmptyLayer())
        self.assertIsNone(combo.currentLayer())

    def test_paletted_renderer_prefills_values(self):
        self.d.landcoverWaterLayerCombo.setLayer(self.paletted)
        self.d.landcoverBuiltUpLayerCombo.setLayer(self.paletted)
        values = [self.d.landcoverWaterValueCombo.itemText(i)
                  for i in range(self.d.landcoverWaterValueCombo.count())]
        self.assertEqual(values, ["10", "50", "80"])
        self.assertEqual(self.d.landcoverWaterValueCombo.currentText(), "80")
        self.assertEqual(self.d.landcoverBuiltUpValueCombo.currentText(), "50")
        self.assertEqual(self.d.landcoverWaterBandCombo.count(), 1)
        self.assertEqual(self.d.landcoverWaterBandCombo.currentData(), 1)

    def test_bands_listed_and_no_values_without_classified_renderer(self):
        self.d.landcoverWaterLayerCombo.setLayer(self.three_band)
        band_combo = self.d.landcoverWaterBandCombo
        self.assertEqual([band_combo.itemData(i) for i in range(band_combo.count())], [1, 2, 3])
        self.assertEqual(band_combo.currentData(), 1)
        self.assertEqual(self.d.landcoverWaterValueCombo.count(), 0)

    def test_value_accepts_integers_only(self):
        from qgis.PyQt.QtGui import QValidator

        validator = self.d.landcoverWaterValueCombo.validator()
        self.assertEqual(validator.validate("80", 0)[0], QValidator.State.Acceptable)
        # Qt reports "8.5" as Intermediate (not Invalid); either way it is never accepted.
        self.assertNotEqual(validator.validate("8.5", 0)[0], QValidator.State.Acceptable)
        self.assertEqual(validator.validate("abc", 0)[0], QValidator.State.Invalid)

    def test_config_from_dialog_mixed_sources(self):
        from tract_geolocation_formatter.landcover import BUILT_UP, WATER

        d = self.d
        d.landcoverWaterCheckBox.setChecked(True)
        self._select(d.landcoverWaterSourceCombo, "project")
        d.landcoverWaterLayerCombo.setLayer(self.three_band)
        d.landcoverWaterBandCombo.setCurrentIndex(1)
        d.landcoverWaterValueCombo.setEditText("7")
        d.landcoverBuiltUpCheckBox.setChecked(True)  # WorldCover (default source)
        config = self.plugin._landcover_config_from_dialog()
        self.assertTrue(config.enabled)
        water, built = config.classes[WATER], config.classes[BUILT_UP]
        self.assertEqual((water.enabled, water.source, water.layer_id, water.band, water.value),
                         (True, "project", self.three_band.id(), 2, "7"))
        self.assertEqual((built.enabled, built.source), (True, "worldcover"))
        self.assertEqual(config.classes_with_source("worldcover"), [BUILT_UP])
        self.assertEqual(config.classes_with_source("project"), [WATER])

    def test_only_one_class_ticked(self):
        from tract_geolocation_formatter.landcover import BUILT_UP, WATER

        self.d.landcoverWaterCheckBox.setChecked(True)
        config = self.plugin._landcover_config_from_dialog()
        self.assertTrue(config.enabled)
        self.assertTrue(config.classes[WATER].enabled)
        self.assertFalse(config.classes[BUILT_UP].enabled)

    def test_ac29_settings_round_trip(self):
        """AC-29 / AC-39: sources and layers are restored; checkboxes start unticked (DEC-23)."""
        d = self.d
        d.landcoverWaterCheckBox.setChecked(True)
        self._select(d.landcoverWaterSourceCombo, "project")
        d.landcoverWaterLayerCombo.setLayer(self.three_band)
        d.landcoverWaterBandCombo.setCurrentIndex(2)
        d.landcoverWaterValueCombo.setEditText("7")
        d.landcoverBuiltUpCheckBox.setChecked(True)
        self._select(d.landcoverBuiltUpSourceCombo, "worldcover")
        self.plugin._save_landcover_settings()

        d.landcoverWaterCheckBox.setChecked(False)
        self._select(d.landcoverWaterSourceCombo, "worldcover")
        d.landcoverWaterLayerCombo.setLayer(None)
        d.landcoverBuiltUpCheckBox.setChecked(False)
        self.plugin._load_landcover_settings()

        self.assertFalse(d.landcoverWaterCheckBox.isChecked())
        self.assertFalse(d.landcoverBuiltUpCheckBox.isChecked())
        self.assertFalse(self.plugin._landcover_config_from_dialog().enabled)
        self.assertEqual(d.landcoverWaterSourceCombo.currentData(), "project")
        self.assertIs(d.landcoverWaterLayerCombo.currentLayer(), self.three_band)
        self.assertEqual(d.landcoverWaterBandCombo.currentData(), 3)
        self.assertEqual(d.landcoverWaterValueCombo.currentText(), "7")
        self.assertEqual(d.landcoverBuiltUpSourceCombo.currentData(), "worldcover")
        # Ticking water again brings back the remembered user layer, ready to use.
        d.landcoverWaterCheckBox.setChecked(True)
        self.assertTrue(d.landcoverWaterLayerCombo.isEnabled())
        self.assertFalse(d.landcoverBuiltUpLayerCombo.isEnabled())

    def test_ac29_removed_layer_shows_as_not_set(self):
        from qgis.core import QgsProject, QgsRasterLayer

        extra = QgsRasterLayer(self.paletted.source(), "temporary", "gdal")
        QgsProject.instance().addMapLayer(extra)
        self.d.landcoverWaterLayerCombo.setLayer(extra)
        self.plugin._save_landcover_settings()
        QgsProject.instance().removeMapLayer(extra.id())
        self.plugin._load_landcover_settings()
        self.assertIsNone(self.d.landcoverWaterLayerCombo.currentLayer())
        self.assertEqual(self.d.landcoverWaterBandCombo.count(), 0)


if __name__ == "__main__":
    unittest.main()
