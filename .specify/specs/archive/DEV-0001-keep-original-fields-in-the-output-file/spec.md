# Spec: Keep Original Fields in the Output File

| Field  | Value      |
|--------|------------|
| Ticket | DEV-0001   |
| Author | Luis Carrasco |
| Date   | 2026-04-14 |

---

## Description

Currently the plugin produces a GeoJSON output with exactly four fixed attributes (`NodeID`, `PlotID`, `TRACTStatus`, `TRACTIssue`). All other attributes from the input layer are discarded during export. This change preserves the original fields from the input layer in the output GeoJSON so users can cross-reference their source data with the TRACT validation results without needing to rejoin the datasets afterward.

## Success Criteria

- [ ] All original fields from the input layer are present in the output GeoJSON alongside the TRACT fields (except mapped fields — see below)
- [ ] TRACT fields (`NodeID`, `PlotID`, `TRACTStatus`, `TRACTIssue`) remain present and behave identically to the current implementation
- [ ] Original field values are preserved as-is (no type conversion or truncation beyond what QGIS/GeoJSON natively handles)
- [ ] Fields mapped to NodeID/PlotID via "Use existing field" are excluded from the original fields (their value lives in the TRACT field)
- [ ] Input fields that clash with TRACT field names are kept with an `_orig` suffix
- [ ] The validation report is unaffected — same columns, same content


## Functional Requirements

- The output GeoJSON includes all fields from the input layer, plus the four TRACT fields (`NodeID`, `PlotID`, `TRACTStatus`, `TRACTIssue`).
- Original fields are always included — there is no UI toggle.
- **Field exclusion:** when the user selects "Use existing field" for NodeID or PlotID, the selected source field is excluded from the original fields in the output. Its value is already in the corresponding TRACT field.
- **Name clash handling:** if an input field has the same name as a TRACT field (`NodeID`, `PlotID`, `TRACTStatus`, `TRACTIssue`) and is NOT the field mapped via "Use existing field", it is renamed with an `_orig` suffix (e.g., `NodeID_orig`, `TRACTStatus_orig`).
- Field ordering: original fields first (minus excluded/renamed ones), then TRACT fields appended at the end.
- Field types from the input layer are preserved as-is (String, Integer, Double, etc.).

## Non-Functional Requirements

- No measurable performance regression for layers with up to 10,000 features and up to 50 fields.


## Constraints (DO NOT)

- Must follow constitution rules (see all files in `.specify/constitutions/**/**`)
- DO NOT change the validation report format or content — this spec only affects the GeoJSON output schema
- DO NOT rename, reorder, or change the type of the four TRACT fields
- DO NOT filter or transform original field values — pass them through as-is

---

## UI Changes

None. Original fields are carried over automatically without user configuration.

## Processing Pipeline Changes

No changes to the geometry processing pipeline itself. The change is limited to how output fields are constructed and how feature attributes are written:

1. **Output field construction** (currently lines 920–925): instead of building `out_fields` with only 4 TRACT fields, copy all fields from the input layer (applying exclusion and rename rules), then append the TRACT fields.
2. **Feature attribute writing** (currently lines 1331–1358): instead of setting only TRACT attributes, copy all non-excluded original attribute values from the input feature, then set the TRACT values.

## Output Changes

### GeoJSON

**Before:** 4 fixed attributes — `NodeID`, `PlotID`, `TRACTStatus`, `TRACTIssue`

**After:** Original input fields (with exclusion/rename rules applied) + `NodeID`, `PlotID`, `TRACTStatus`, `TRACTIssue` appended

**Example 1** — input has `farm_name`, `area_declared`, `region`; user selects auto-generate for NodeID, no PlotID:

```json
{
  "properties": {
    "farm_name": "Fazenda Sol",
    "area_declared": 12.5,
    "region": "Mato Grosso",
    "NodeID": "NODE_1",
    "PlotID": "",
    "TRACTStatus": "READY",
    "TRACTIssue": ""
  }
}
```

**Example 2** — input has `farm_id`, `NodeID`, `plot_code`; user maps `farm_id` → NodeID (existing field), `plot_code` → PlotID (existing field):

```json
{
  "properties": {
    "NodeID_orig": "old-node-value",
    "NodeID": "FARM_42",
    "PlotID": "PLT_007",
    "TRACTStatus": "READY",
    "TRACTIssue": ""
  }
}
```

Here: `farm_id` is excluded (mapped to NodeID), `plot_code` is excluded (mapped to PlotID), `NodeID` from input is renamed to `NodeID_orig`.

### Validation Report

No changes.


## Technical Context

- **Affected area:** output field construction and feature attribute writing in `_run_transformation_from_dialog`
- **Key code locations:**
  - `out_fields` definition: `TRACT_Geolocation_Formatter.py` lines 920–925
  - Feature attribute assignment: `TRACT_Geolocation_Formatter.py` lines 1331–1358
- **QGIS API:** `QgsFields`, `QgsField`, `QgsFeature.attributes()`, `QgsFeature.__setitem__`, `layer.fields()`
- **Constitution impact:** Constitution § 3 (Output Contracts) requires amendment — see DEC-2 in decision-log.md


## Acceptance Criteria

1. **AC-1:** GIVEN an input layer with fields `[farm_name, region, id]` and auto-generated NodeID, WHEN the plugin runs, THEN the output GeoJSON contains properties `farm_name`, `region`, `id`, `NodeID`, `PlotID`, `TRACTStatus`, `TRACTIssue` with correct values.

2. **AC-2:** GIVEN an input layer with field `farm_id` and the user selects "Use existing field" → `farm_id` for NodeID, WHEN the plugin runs, THEN `farm_id` does NOT appear in the output properties, and `NodeID` contains the value from `farm_id`.

3. **AC-3:** GIVEN an input layer with fields `[region, NodeID]` and the user selects "Auto-generate" for NodeID, WHEN the plugin runs, THEN the output contains `region` (unchanged), `NodeID_orig` (with the original NodeID value), and `NodeID` (with the auto-generated value).

4. **AC-4:** GIVEN an input layer with fields `[data, TRACTStatus]`, WHEN the plugin runs, THEN the output contains `data` (unchanged), `TRACTStatus_orig` (with the original value), and `TRACTStatus` (with the TRACT-computed value).

5. **AC-5:** GIVEN an input layer with fields of various types (String, Integer, Double, Date), WHEN the plugin runs, THEN all original field types are preserved in the output GeoJSON (within GeoJSON type limitations).

6. **AC-6:** GIVEN an input layer with no issues (all features READY), WHEN the plugin runs, THEN the validation report is identical to what it would have been before this change.

7. **AC-7:** GIVEN an input layer with field `PlotID` and the user selects "Use existing field" → `PlotID` for PlotID, WHEN the plugin runs, THEN the input `PlotID` field is NOT renamed to `PlotID_orig` — it is excluded, and the TRACT `PlotID` carries its value.


## Open Questions

All resolved — see `clarify.md`.


## Changelog

| Date       | Author | Change        |
|------------|--------|---------------|
| 2026-04-14 | Luis Carrasco | Initial draft |
| 2026-04-14 | Luis Carrasco | Updated after Q1–Q3 clarification: always include fields, `_orig` suffix for clashes, exclude mapped fields |
