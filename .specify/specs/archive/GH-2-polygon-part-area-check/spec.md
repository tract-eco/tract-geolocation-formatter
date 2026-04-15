# Spec: Check minimum area on individual polygon parts

| Field  | Value      |
|--------|------------|
| Ticket | [GH-2](https://github.com/tract-eco/tract-geolocation-formatter/issues/2) |
| Author | Luis Carrasco |
| Date   | 2026-04-15 |

---

## Description

Currently the minimum area check (0.05 ha) runs on the entire geometry using `geom.area()`. For multipolygon features, this means a feature can pass the threshold overall while containing very small polygon parts (slivers, artifacts) that individually fall below the minimum.

The TRACT platform validation workflow checks area at the individual polygon part level. This misalignment means features can pass the plugin validation but fail during TRACT ingestion. The plugin should align with TRACT's behavior — evaluate each polygon part separately when the geometry is a multipolygon, and flag any part that falls below the threshold.

## Success Criteria

- [ ] For multipolygon features, the area check evaluates each polygon part individually against the 0.05 ha threshold
- [ ] For simple polygon features, the area check behavior is unchanged (whole geometry)
- [ ] Each failing polygon part is reported with its specific area in the validation report
- [ ] The validation report message identifies which part failed (e.g., part index)
- [ ] Features where any part fails the area check are marked as `NEEDS_FIX`


## Functional Requirements

- When the geometry is a multipolygon, iterate over each polygon part and compute its area independently.
- If any individual part has area below `MIN_PLOT_AREA_HA` (0.05 ha), flag the feature as `NEEDS_FIX`.
- The validation report should include one row per failing part, with the part index and its area.
- The whole-geometry area check is kept as well — if the total geometry area is below the threshold, that is also reported (a single polygon that is too small).
- For simple (non-multi) polygons, the behavior is unchanged: check the whole geometry area.

## Non-Functional Requirements

- No measurable performance regression. Area computation per part is lightweight compared to the geometry processing already happening.


## Constraints (DO NOT)

- Must follow constitution rules (see all files in `.specify/constitutions/**/**`)
- DO NOT remove the whole-geometry area check — add the per-part check alongside it
- DO NOT modify the `MIN_PLOT_AREA_HA` constant or the `AREA_CRS` projection
- DO NOT auto-fix small parts (e.g., by removing them) — this is a detection-only check

---

## UI Changes

None.

## Processing Pipeline Changes

The change is confined to the minimum area check section in `_run_transformation_from_dialog` (currently lines 1291–1325). After the existing whole-geometry area check, add a per-part check for multipolygon geometries:

1. If `geom.isMultipart()`, extract individual polygon parts via `asMultiPolygon()`
2. For each part, create a `QgsGeometry.fromPolygonXY(part)`, transform to EPSG:6933, compute area
3. If any part's area < `MIN_PLOT_AREA_HA`, flag it with part index and area in the validation report

Pipeline position: stage 8 (minimum area check) — no change to the pipeline order.

## Output Changes

### GeoJSON

No schema changes. `TRACTStatus` and `TRACTIssue` fields are already present. A feature with a failing part will have `NEEDS_FIX` status and the issue listed in `TRACTIssue`.

### Validation Report

New `issue_type` value:

| `issue_type` | `status` | Example message |
|--------------|----------|-----------------|
| `small_area_part` | ERROR | `Polygon part 2 area below minimum (0.0120 ha < 0.05 ha)` |

The existing `small_area` issue type is preserved for the whole-geometry check.


## Technical Context

- **Affected area:** minimum area check in `_run_transformation_from_dialog` (lines 1291–1325)
- **Key code:**
  - `area_geom.transform(area_transform)` + `area_geom.area()` — existing area computation pattern
  - `geom.isMultipart()` / `geom.asMultiPolygon()` — already used in holes detection (lines 1330–1335)
- **QGIS API:** `QgsGeometry.fromPolygonXY(part)` to create individual part geometries for area computation
- **Constants:** `MIN_PLOT_AREA_HA = 0.05`, `AREA_CRS = EPSG:6933` — unchanged
- **Domain alignment:** TRACT platform checks area per polygon part, not per feature


## Acceptance Criteria

1. **AC-1:** GIVEN a multipolygon feature with 3 parts where all parts are >= 0.05 ha, WHEN the plugin runs, THEN no area issue is reported for that feature.

2. **AC-2:** GIVEN a multipolygon feature with 3 parts where part 2 is 0.01 ha, WHEN the plugin runs, THEN the feature is marked `NEEDS_FIX` and the validation report contains a row with `issue_type=small_area_part` and a message mentioning part 2 and its area.

3. **AC-3:** GIVEN a multipolygon feature where the total area is >= 0.05 ha but one part is 0.02 ha, WHEN the plugin runs, THEN the whole-geometry check passes but the per-part check flags the small part.

4. **AC-4:** GIVEN a simple (non-multi) polygon feature with area 0.03 ha, WHEN the plugin runs, THEN the existing `small_area` check fires as before (no per-part check needed).

5. **AC-5:** GIVEN a multipolygon with 2 parts both below 0.05 ha, WHEN the plugin runs, THEN both parts are reported individually in the validation report (2 rows with `small_area_part`).

6. **AC-6:** GIVEN a multipolygon where the total area is below 0.05 ha, WHEN the plugin runs, THEN both the whole-geometry `small_area` and the per-part `small_area_part` issues are reported.


## Open Questions

All resolved — see `clarify.md`.


## Changelog

| Date       | Author | Change        |
|------------|--------|---------------|
| 2026-04-15 | Luis Carrasco | Initial draft |
| 2026-04-15 | Luis Carrasco | Confirmed 1-based part indexing and skip per-part for simple polygons |
