"""
Start the shared QgsApplication before any other test module is imported.

``unittest discover`` imports test modules in alphabetical order, so this module loads
first. On QGIS 3.38, creating a CRS (e.g. while importing the plugin module) before the
QgsApplication is initialised leaves CRS handling broken for the whole process: rasters
opened later get an invalid CRS. Inside QGIS the application always exists first, so this
only affects the test run. Contains no tests; does nothing without QGIS.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import qgis.core  # noqa: F401
except ImportError:
    pass
else:
    from _qgis_app import qgis_app

    qgis_app()
