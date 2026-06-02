# -*- coding: utf-8 -*-
"""
Dialog wrapper for TRACT Geolocation Formatter
"""

import os

from qgis.PyQt import uic, QtWidgets

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'TRACT_Geolocation_Formatter_dialog_base.ui')
)


class TractGeolocationFormatterDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # Add static tool description
        self.logTextEdit.setPlainText(
            "This tool converts polygon layers into TRACT's standardized geolocation GeoJSON format.\n\n"
            "It automatically validates and repairs common geometry issues:\n"
            "- Removal of consecutive duplicate vertices\n"
            "- Geometry validation and repair (makeValid)\n"
            "- Removal of Z values\n"
            "- Coordinate rounding\n"
            "- Reprojection to EPSG:4326\n\n"
            "The tool also performs data quality checks:\n"
            "- Minimum polygon area validation\n"
            "- Detection of polygons with interior holes\n"
            "- Identification of empty or invalid geometries\n\n"
            "Configure NodeID and PlotID options and export a clean "
            "TRACT-compatible GeoJSON file together with a validation report."
        )
