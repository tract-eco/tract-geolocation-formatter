# Convention: Testing

Approach to testing the QGIS plugin.

---

## Current State

The `tests/` directory exists with an empty `__init__.py`. No tests are written yet. New features should include tests where feasible.

## Testing Challenges

QGIS plugins are tightly coupled to the QGIS runtime (`QgsInterface`, `QgsProject`, `QgsVectorLayer`, etc.). Full integration tests require a running QGIS instance or `qgis.testing` infrastructure.

## Recommended Approach

### Unit Tests (preferred for new code)

- **Geometry helper methods** (`_truncate_geometry_coordinates`, `_fix_duplicate_vertices`, `_has_boundary_self_intersections`, etc.) can be tested independently if they only depend on `QgsGeometry` and not on `self.iface` or dialog state.
- If extracting geometry helpers to a separate module (see `conventions/plugin-structure.md`), they become straightforward to unit test.
- Use `pytest` as the test runner.
- Test files: `tests/test_*.py`.

### Integration Tests (when needed)

- Use `qgis.testing` utilities or the `pytest-qgis` plugin to bootstrap a QGIS environment.
- Test the full pipeline with known input layers and verify output GeoJSON structure and validation report content.

## Test Data

- Store test fixtures (small GeoJSON/GeoPackage files with known geometry issues) in `tests/fixtures/`.
- Keep test data minimal — a few features per file is enough to cover each geometry check.

## What to Test

Priority order for adding tests:

1. Geometry helpers (truncation, duplicate removal, polygon extraction)
2. TRACT geometry checks (duplicate vertices, ring validation, self-intersections)
3. NodeID / PlotID assignment logic
4. Full pipeline with fixture data (integration)
