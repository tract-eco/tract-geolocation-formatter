# Domain: Geometry Validation

Covers all geometry checks and repairs performed by the plugin.

---

## Scope

This domain covers the detection and automatic repair of geometry issues in input polygon layers, as well as the final TRACT-aligned validation checks.

## Auto-Repaired Issues (WARNING)

These issues are detected and fixed automatically. They appear as `WARNING` in the validation report:

| Issue | Detection | Fix | Pipeline Stage |
|-------|-----------|-----|----------------|
| Z values present | `QgsWkbTypes.hasZ(wkbType)` | Dropped at write time via 2D WKB type | After load |
| Coordinate excess precision | Coordinates differ after truncation | `_truncate_geometry_coordinates` (math.trunc) | After reprojection |
| Consecutive duplicate vertices | Adjacent identical coordinates | `_fix_duplicate_vertices` (clean ring) | After truncation |
| GEOS-invalid geometry | `not geom.isGeosValid()` | `geom.makeValid()` + `_extract_polygonal_geometry` | After duplicate fix |

## Manual-Fix Issues (ERROR)

These issues are detected but cannot be auto-repaired. They set `TRACTStatus = "NEEDS_FIX"` and appear as `ERROR`:

| Issue | Detection | User Action Required |
|-------|-----------|---------------------|
| makeValid failed | Empty result after makeValid | Manually fix the geometry in QGIS |
| Still invalid after makeValid | `not fixed.isGeosValid()` after repair | Manually simplify or redraw |
| Duplicate vertices in rings | Non-unique coords in ring body (set check) | Remove duplicate points manually |
| Fewer than 3 unique coords | Ring body has < 3 distinct points | Polygon is degenerate — redraw |
| Boundary self-intersections | Shapely: `not boundary.is_simple` | Resolve self-crossing boundaries |
| Area below minimum | Area < 0.05 ha (EPSG:6933) | Merge with adjacent polygon or remove |
| Interior holes | Ring count > 1 in any polygon part | Remove holes or split into separate polygons |

## Skipped Features

Features that are skipped entirely (not written to output):

- Empty geometry
- Null geometry
- Reprojection error
- Geometry becomes empty after truncation
- Geometry becomes empty/invalid after duplicate vertex fix
- Area computation failure

## Key Code Locations

- Auto-repairs and checks: `_run_transformation_from_dialog` (main loop)
- Geometry helpers: `_truncate_geometry_coordinates`, `_fix_duplicate_vertices`, `_extract_polygonal_geometry`
- TRACT checks: `_get_tract_geometry_errors`, `_has_duplicate_vertices_in_rings`, `_has_rings_with_fewer_than_three_unique_coords`, `_has_boundary_self_intersections`
