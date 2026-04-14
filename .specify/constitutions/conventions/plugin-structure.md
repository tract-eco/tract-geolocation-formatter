# Convention: Plugin Structure

How the QGIS plugin is organized and how components relate to each other.

---

## File Layout

```
tract_geolocation_formatter/
├── __init__.py                                  # Entry point: classFactory(iface)
├── TRACT_Geolocation_Formatter.py               # Main plugin class (all logic)
├── TRACT_Geolocation_Formatter_dialog.py        # Dialog wrapper (custom init logic)
├── TRACT_Geolocation_Formatter_dialog_base.py   # Generated from .ui (DO NOT EDIT)
├── TRACT_Geolocation_Formatter_dialog_base.ui   # Qt Designer UI file (edit this)
├── metadata.txt                                 # QGIS plugin metadata
├── icon.png                                     # Plugin icon
├── resources.qrc                                # Qt resource file
├── resources_rc.py                              # Compiled resources
├── i18n/                                        # Translations
└── scripts/                                     # Dev/build helper scripts
```

## Plugin Lifecycle

1. **Load:** QGIS calls `classFactory(iface)` → returns `TractGeolocationFormatter(iface)`
2. **Init GUI:** QGIS calls `initGui()` → registers toolbar icon and menu entry
3. **Run:** user clicks icon → `run()` → populates and shows dialog → on OK, runs transformation
4. **Unload:** QGIS calls `unload()` → removes menu/toolbar entries

## Dialog Pattern

- The `.ui` file is the source of truth for the dialog layout. Edit it in Qt Designer.
- Regenerate the base class: `pyuic5 -o TRACT_Geolocation_Formatter_dialog_base.py TRACT_Geolocation_Formatter_dialog_base.ui`
- The dialog wrapper (`_dialog.py`) inherits from both `QDialog` and the generated `Ui_*` base. Put custom initialization (e.g., static text, signal connections that belong to the dialog itself) here.
- Signal connections that depend on plugin state (layer changes, radio button logic) belong in the main class, not the dialog.

## Adding New Functionality

- **New geometry check or fix:** add a private method (`_check_xxx` or `_fix_xxx`) to the main class, then call it from `_run_transformation_from_dialog` at the correct pipeline stage.
- **New UI control:** edit the `.ui` file, regenerate the base, then wire signals in the main class.
- **New output attribute:** update `out_fields` in `_run_transformation_from_dialog` and update the TRACT template documentation.
- **Extracting modules:** if the main class exceeds ~1500 lines, consider extracting geometry helpers into `tract_geolocation_formatter/geometry.py` or similar. Keep imports minimal — only the main class should interact with QGIS dialog and project APIs.
