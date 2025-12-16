# -*- coding: utf-8 -*-
"""
Dialog wrapper for TRACT Geolocation Formatter
"""

from qgis.PyQt import QtWidgets
from .TRACT_Geolocation_Formatter_dialog_base import Ui_TractGeolocationFormatterDialogBase

class TractGeolocationFormatterDialog(QtWidgets.QDialog, Ui_TractGeolocationFormatterDialogBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # Add static tool description
        self.logTextEdit.setPlainText(
            "This tool converts polygon geometries into TRACT's standardized geolocation format.\n\n"
            "It also applies automatic geometry fixes:\n"
            "- Removal of consecutive duplicate vertices\n"
            "- Geometry validation (makeValid)\n"
            "- Reprojection to EPSG:4326\n\n"
            "Choose NodeID / PlotID options and export a clean TRACT-compliant GeoJSON file."
        )