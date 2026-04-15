# Plan: Check minimum area on individual polygon parts

> **Ticket:** GH-2
> **Date:** 2026-04-15

Technical design for implementing the spec. All decisions must respect all files in `.specify/constitutions/**/**`.

---

## UI Changes

None.

## Processing Pipeline Changes

No change to pipeline order. The change adds a per-part area check immediately after the existing whole-geometry area check (pipeline stage 8).

### Modified: `_run_transformation_from_dialog`

**After the existing whole-geometry area check block (line 1325), add:**

```python
# Per-part minimum area check (multipolygons only)
if geom.isMultipart():
    multipoly = geom.asMultiPolygon()
    for part_idx, part in enumerate(multipoly, start=1):
        try:
            part_geom = QgsGeometry.fromPolygonXY(part)
            part_area_geom = QgsGeometry(part_geom)
            part_area_geom.transform(area_transform)
            part_area_m2 = part_area_geom.area()
            part_area_ha = part_area_m2 / 10000.0
        except Exception:
            continue

        if part_area_ha < MIN_PLOT_AREA_HA:
            feature_status = "NEEDS_FIX"
            feature_issues.append(
                f"Polygon part {part_idx} area below minimum "
                f"({part_area_ha:.4f} ha < {MIN_PLOT_AREA_HA} ha)"
            )

            node_id, plot_id = self._get_ids(
                f, layer,
                node_use_existing, node_field_name,
                node_same, node_same_value,
                plot_existing, plot_field_name,
            )

            validation_rows.append({
                "feature_id": f.id(),
                "NodeID": node_id,
                "PlotID": plot_id,
                "status": "ERROR",
                "issue_type": "small_area_part",
                "message": (
                    f"Polygon part {part_idx} area below minimum "
                    f"({part_area_ha:.4f} ha < {MIN_PLOT_AREA_HA} ha)"
                ),
            })
```

**Key design points:**

- Uses `enumerate(multipoly, start=1)` for 1-based part indexing (per Q1 clarification).
- Only runs for multipolygons (per Q2 clarification). Simple polygons are already covered by the whole-geometry check.
- Uses the same `area_transform` (EPSG:6933) already computed earlier in the method.
- Follows the same pattern as the existing whole-geometry check: set `feature_status`, append to `feature_issues`, call `_get_ids`, append to `validation_rows`.
- Each failing part produces its own validation row with `issue_type=small_area_part`.
- If `QgsGeometry.fromPolygonXY(part)` or the transform fails for a specific part, it is silently skipped (the feature-level area check already passed or failed).

## Output Changes

### GeoJSON Attribute Changes

No schema changes. `TRACTIssue` will contain additional messages for per-part failures (semicolon-separated, same as existing issues).

### Validation Report Changes

| issue_type | status | message | Description |
|------------|--------|---------|-------------|
| `small_area_part` | ERROR | `Polygon part {N} area below minimum ({X} ha < 0.05 ha)` | Individual polygon part below threshold |

Existing `small_area` issue type unchanged.

## Component Structure

Files to create or modify:

### Plugin Logic
- [ ] `tract_geolocation_formatter/TRACT_Geolocation_Formatter.py` — add per-part area check block after the existing whole-geometry area check (inside the main feature loop in `_run_transformation_from_dialog`)

### Tests
- [ ] `tests/test_per_part_area_check.py` — unit/integration tests covering AC-1 through AC-6

### Domain Docs
- [ ] `.specify/constitutions/domains/geometry-validation.md` — add `small_area_part` to the Manual-Fix Issues table
- [ ] `.specify/constitutions/domains/validation-report.md` — add `small_area_part` to the Issue Types table

---

## Integration Points

Existing code to reuse or connect to:

| File / Method | What to reuse | How |
|---------------|--------------|-----|
| `TRACT_Geolocation_Formatter.py:1291-1325` | Existing whole-geometry area check | Follow the same pattern (transform, compute, compare, report) |
| `TRACT_Geolocation_Formatter.py:1330-1335` | Holes detection `isMultipart()` → `asMultiPolygon()` loop | Same iteration pattern for per-part area |
| `TRACT_Geolocation_Formatter.py:1293-1294` | `area_transform` (already computed) | Reuse for per-part transforms |
| `TRACT_Geolocation_Formatter.py:494-522` | `_get_ids` helper | Call for each validation row, same as other checks |
| `qgis.core.QgsGeometry.fromPolygonXY(part)` | QGIS API | Create standalone geometry from each multipolygon part |

## Risks & Considerations

- **`fromPolygonXY` with interior rings:** each `part` from `asMultiPolygon()` is a list of rings (exterior + holes). `QgsGeometry.fromPolygonXY(part)` handles this correctly — the area includes holes (they reduce the area). This is the correct behavior since TRACT checks the polygon part as a whole including its holes.
- **Performance:** for a feature with N parts, we compute N additional area transforms. Typical multipolygons have 2–5 parts. Even with 1000 features × 5 parts = 5000 transforms — negligible.
- **No new helper method needed:** the logic is a simple loop and fits naturally inline after the existing area check. Extracting to a helper would be premature for a single-use block.
