# Tasks: Keep Original Fields in the Output File

> **Ticket:** DEV-0001
> **Date:** 2026-04-14

Discrete, independently testable units. Each task targets a focused set of changes.

---

## Legend

- `[P]` — Can run in parallel with other `[P]` tasks at the same level
- `[B]` — Blocked by the task(s) listed in "Depends on"
- **AC-N** — References acceptance criterion N from the spec

## Task Breakdown

### Task 1: Add `_build_output_fields` helper and `TRACT_FIELD_NAMES` constant - [x] (2026-04-14)

- **Description:** Add the `TRACT_FIELD_NAMES` constant at module level and implement the `_build_output_fields` method on the main plugin class. This method takes the input layer's `QgsFields` and a set of excluded field names, and returns the combined output `QgsFields` plus a rename map for clashing fields. This is a pure addition — existing behavior is not changed yet.
- **Depends on:** None
- **Files:**
  - Modify: `tract_geolocation_formatter/TRACT_Geolocation_Formatter.py`
- **Acceptance criteria covered:** None directly (foundation for AC-1 through AC-5, AC-7)
- **Verification:** Method exists and is callable. Verified by Task 2 tests.

---

### Task 2: Unit tests for `_build_output_fields` `[P]` - [x] (2026-04-14)

- **Description:** Create unit tests for the new helper method covering: basic field passthrough with TRACT fields appended, excluded fields are omitted, clashing field names get `_orig` suffix, mapped fields that clash are excluded (not renamed), and mixed scenarios.
- **Depends on:** Task 1
- **Files:**
  - Create: `tests/test_build_output_fields.py`
- **Acceptance criteria covered:** AC-1 (field presence), AC-2 (mapped field excluded), AC-3 (clash rename), AC-4 (TRACTStatus clash), AC-5 (type preservation), AC-7 (mapped clash excluded)
- **Verification:** `cd tract_geolocation_formatter && python -m pytest ../tests/test_build_output_fields.py -v` (requires QGIS Python environment or mocked QgsFields)

---

### Task 3: Wire `_build_output_fields` into the transformation pipeline and copy original attributes `[P]` - [x] (2026-04-14)

- **Description:** Modify `_run_transformation_from_dialog` to: (1) build the `excluded_fields` set from `node_use_existing`/`node_field_name` and `plot_existing`/`plot_field_name`, (2) replace the hardcoded 4-field `out_fields` construction with a call to `_build_output_fields`, (3) add the attribute copy loop before the existing NodeID/PlotID/TRACTStatus/TRACTIssue assignment block so original values are written to output features.
- **Depends on:** Task 1
- **Files:**
  - Modify: `tract_geolocation_formatter/TRACT_Geolocation_Formatter.py`
- **Acceptance criteria covered:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-7
- **Verification:** Manual test in QGIS:
  1. Load a polygon layer with several attribute fields
  2. Run the plugin with "Auto-generate" NodeID, "No PlotID"
  3. Inspect the output GeoJSON — original fields should be present alongside TRACT fields
  4. Run again with "Use existing field" for NodeID — the mapped field should be absent from output, its value in `NodeID`
  5. If the input has a field named `NodeID` and you use "Auto-generate", confirm `NodeID_orig` appears with the original value

---

### Task 4: Update constitution and domain docs `[P]` - [x] (2026-04-14)

- **Description:** Amend constitution § 3 (Output Contracts) to state that GeoJSON output must contain "at minimum" the four TRACT attributes, with original input fields preserved alongside them. Update `tract-template.md` domain file to document the new attribute behavior including exclusion and `_orig` rename rules.
- **Depends on:** Task 1
- **Files:**
  - Modify: `.specify/constitutions/constitution.md`
  - Modify: `.specify/constitutions/domains/tract-template.md`
- **Acceptance criteria covered:** None directly (documentation alignment with DEC-2)
- **Verification:** Read updated files and confirm they accurately describe the new output behavior.

---

### Task 5: End-to-end validation `[B]` - [x] (2026-04-14)

- **Description:** Full manual validation of all acceptance criteria in QGIS. Test with multiple input layers covering all AC scenarios: basic field passthrough (AC-1), mapped field exclusion (AC-2), NodeID clash with auto-generate (AC-3), TRACTStatus clash (AC-4), mixed field types (AC-5), validation report unchanged (AC-6), mapped PlotID clash exclusion (AC-7).
- **Depends on:** Task 2, Task 3, Task 4
- **Files:**
  - None (testing only)
- **Acceptance criteria covered:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7
- **Verification:** All 7 acceptance criteria pass in QGIS with test layers. Validation report CSV is unchanged in structure and content compared to before the change.

## Dependency Graph

```
Task 1 (helper + constant)
├── Task 2 [P] (unit tests)
├── Task 3 [P] (wire into pipeline)
├── Task 4 [P] (docs update)
└── Task 5 [B] (e2e validation, after 2 + 3 + 4)
```

## Uncovered Acceptance Criteria

- None (all covered)
