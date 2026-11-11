"""
Shared QgsApplication for tests that need QGIS objects (layers, providers, processing,
widgets). Created once per test process, offscreen.

Settings written through QgsSettings/QSettings during tests are redirected to a
throw-away INI folder, so a test run never touches the user's real QGIS settings.
"""

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_APP = None
SETTINGS_DIR = tempfile.mkdtemp(prefix="tract_tests_settings_")


def qgis_app():
    """Return the running QgsApplication, creating and initialising it if needed."""
    global _APP
    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import QCoreApplication, QSettings

    if _APP is not None:
        return _APP
    existing = QgsApplication.instance()
    if existing is not None:
        _APP = existing
        return _APP
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS_DIR)
    # A throw-away profile folder: QGIS writes its style database and other profile
    # files there instead of the working directory or the user's real profile.
    _APP = QgsApplication([], True, SETTINGS_DIR)
    QCoreApplication.setOrganizationName("TRACTTests")
    QCoreApplication.setApplicationName("tract-geolocation-formatter-tests")
    _APP.initQgis()
    return _APP
