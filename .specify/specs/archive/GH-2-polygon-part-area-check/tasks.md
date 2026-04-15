# Tasks: Check minimum area on individual polygon parts

> **Ticket:** GH-2
> **Date:** 2026-04-15

Discrete, independently testable units. Each task targets a focused set of changes.

---

## Legend

- `[P]` — Can run in parallel with other `[P]` tasks at the same level
- `[B]` — Blocked by the task(s) listed in "Depends on"
- **AC-N** — References acceptance criterion N from the spec

## Task Breakdown

### Task 1: Add per-part area check for multipolygon features - [x] (2026-04-15)

- **Description:** Add the per-part minimum area check block in `_run_transformation_from_dialog`, immediately after the existing whole-geometry area check. For multipolygon geometries, iterate over each polygon part using `asMultiPolygon()`, compute area via EPSG:6933 transform, and flag any part below `MIN_PLOT_AREA_HA` with `issue_type=small_area_part` and 1-based part indexing. Skip for simple polygons.
- **Depends on:** None
- **Files:**
  - Modify: `tract_geolocation_formatter/TRACT_Geolocation_Formatter.py`
- **Acceptance criteria covered:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-6
- **Verification:** Manual test in QGIS:
  1. Load a multipolygon layer where one part is a sliver (< 0.05 ha) but the total feature area is above threshold
  2. Run the plugin and inspect the output GeoJSON — feature should be `NEEDS_FIX` with `TRACTIssue` mentioning the specific part
  3. Inspect the validation report CSV — should contain a row with `issue_type=small_area_part`
  4. Run with a simple polygon below 0.05 ha — should only get `small_area`, not `small_area_part`

---

### Task 2: Update domain docs `[P]` - [x] (2026-04-15)

- **Description:** Add `small_area_part` to the Manual-Fix Issues table in `geometry-validation.md` and to the Issue Types table in `validation-report.md`.
- **Depends on:** Task 1
- **Files:**
  - Modify: `.specify/constitutions/domains/geometry-validation.md`
  - Modify: `.specify/constitutions/domains/validation-report.md`
- **Acceptance criteria covered:** None directly (documentation alignment)
- **Verification:** Read updated files and confirm `small_area_part` is documented.

---

### Task 3: End-to-end validation `[B]` - [x] (2026-04-15)

- **Description:** Full manual validation of all acceptance criteria in QGIS. Test with multipolygon layers covering: all parts above threshold (AC-1), one small part (AC-2), total above but part below (AC-3), simple polygon below threshold (AC-4), multiple small parts (AC-5), total and parts both below (AC-6).
- **Depends on:** Task 1, Task 2
- **Files:**
  - None (testing only)
- **Acceptance criteria covered:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-6
- **Verification:** All 6 acceptance criteria pass in QGIS with test layers.

## Dependency Graph

```
Task 1 (per-part area check)
├── Task 2 [P] (docs update)
└── Task 3 [B] (e2e validation, after 1 + 2)
```

## Uncovered Acceptance Criteria

- None (all covered)
