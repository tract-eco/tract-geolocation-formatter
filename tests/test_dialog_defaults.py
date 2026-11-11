"""
Dialog defaults (GH-12 DEC-20): the polygon overlap check starts unticked with a 0 %
threshold, every time the dialog is populated. QGIS Python only; skipped elsewhere.
"""

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

try:
    from qgis.core import QgsProject  # noqa: F401

    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


@unittest.skipUnless(QGIS_AVAILABLE, "Requires QGIS Python environment")
class OverlapDefaultsTests(unittest.TestCase):
    def setUp(self):
        from _qgis_app import qgis_app
        from qgis.PyQt.QtCore import QSettings

        qgis_app()
        QSettings().setValue("locale/userLocale", "en_US")  # temp INI (see _qgis_app)

    def test_overlap_check_off_and_threshold_zero(self):
        from qgis.PyQt import sip

        import tract_geolocation_formatter.TRACT_Geolocation_Formatter as M

        p = M.TractGeolocationFormatter.__new__(M.TractGeolocationFormatter)
        p.dlg = M.TractGeolocationFormatterDialog()
        try:
            # The .ui itself, before the plugin populates it.
            self.assertFalse(p.dlg.overlapCheckBox.isChecked())
            self.assertEqual(p.dlg.overlapThresholdSpin.value(), 0.0)
            # And after population, even if the user changed them on a previous open.
            p.dlg.overlapCheckBox.setChecked(True)
            p.dlg.overlapThresholdSpin.setValue(5.0)
            p._connect_landcover_signals()
            p._populate_dialog()
            self.assertFalse(p.dlg.overlapCheckBox.isChecked())
            self.assertFalse(p.dlg.overlapContainer.isEnabled())
            self.assertEqual(p.dlg.overlapThresholdSpin.value(), 0.0)
        finally:
            sip.delete(p.dlg)


if __name__ == "__main__":
    unittest.main()
