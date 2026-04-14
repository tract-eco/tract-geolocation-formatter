# Convention: Geometry Processing

Patterns and rules for geometry manipulation in the plugin.

---

## General Rules

- All geometry manipulation uses `QgsGeometry` from `qgis.core`. Shapely is only used for the boundary self-intersection check.
- Helper methods are private (`_` prefix) and operate on `QgsGeometry` objects. They return new `QgsGeometry` instances — never mutate the input.
- Handle both `Polygon` and `MultiPolygon` explicitly. Use `geom.isMultipart()` to branch, then `asPolygon()` / `asMultiPolygon()` accordingly.
- Always check `geom.isEmpty()` at the top of any helper.

## Coordinate Truncation

- Use `math.trunc()`, not `round()`. Truncation is deterministic and avoids rounding-induced coordinate drift.
- Truncation happens once, after reprojection, before all other checks.
- After truncation, geometries may become invalid (duplicate vertices, self-intersections). The pipeline handles this — do not skip truncation to avoid invalidity.

## Geometry Repair Pipeline

```
reproject → truncate → fix duplicates → makeValid → extract polygonal → TRACT checks
```

- `makeValid()` may return a `GeometryCollection`. Always call `_extract_polygonal_geometry()` afterward to recover only polygon parts.
- If repair fails (empty result or still invalid), keep the original geometry and mark the feature as `NEEDS_FIX`. Do not skip or silently drop features.

## Area Calculations

- Transform to EPSG:6933 (equal-area CRS) before computing area.
- Compare area in hectares: `area_m2 / 10000.0`.
- The minimum threshold is defined by `MIN_PLOT_AREA_HA` constant.

## TRACT Geometry Checks

These are the final validation checks, run after all repairs:

1. **Duplicate vertices in rings** — any non-unique coordinate in a ring body (excluding closing vertex).
2. **Fewer than 3 unique coordinates** — each ring must have at least 3 distinct points.
3. **Boundary self-intersections** — uses Shapely: `not shape(geojson).boundary.is_simple`.

These checks are purely diagnostic — they set `NEEDS_FIX` status but do not modify the geometry.

## Validation Rows

Every check or repair that fires must append a row to `validation_rows` with:
- `feature_id`, `NodeID`, `PlotID` — identifying the feature
- `status` — `"WARNING"` for auto-fixed issues, `"ERROR"` for issues requiring manual intervention
- `issue_type` — machine-readable category (e.g., `"duplicate_vertices"`, `"small_area"`)
- `message` — human-readable description
