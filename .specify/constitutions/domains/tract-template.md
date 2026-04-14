# Domain: TRACT GeoJSON Template

Covers the output GeoJSON format and attribute schema expected by the TRACT platform.

---

## Output GeoJSON Structure

The plugin produces a standard GeoJSON `FeatureCollection`. The file is written using `QgsVectorFileWriter` with the `GeoJSON` driver.

### Attributes

The output contains all original input fields (with rules below) plus the four TRACT fields appended at the end.

#### TRACT Fields (always present)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `NodeID` | String | Yes | Identifies the sourcing node (farm, cooperative, etc.) |
| `PlotID` | String | No | Identifies an individual plot within a node |
| `TRACTStatus` | String | Yes | `"READY"` or `"NEEDS_FIX"` |
| `TRACTIssue` | String | No | Semicolon-separated list of detected issues (empty if READY) |

#### Original Input Fields

All fields from the input layer are carried over, subject to these rules:

| Rule | Condition | Behavior |
|------|-----------|----------|
| **Exclusion** | Field is selected as NodeID or PlotID source via "Use existing field" | Field is excluded — its value is already in the TRACT field |
| **Rename** | Field name clashes with a TRACT field name (`NodeID`, `PlotID`, `TRACTStatus`, `TRACTIssue`) and is NOT excluded | Renamed with `_orig` suffix (e.g., `NodeID_orig`) |
| **Passthrough** | All other fields | Kept as-is with original name and type |

Field ordering: original fields first (with exclusion/rename applied), then TRACT fields.

### NodeID Assignment Options

Users choose one of three methods via the dialog:

1. **Existing field** — map a field from the input layer to NodeID (source field is excluded from output)
2. **Same value** — assign a fixed string to all features (e.g., `"NODE_001"`)
3. **Auto-generate** — sequential integers with optional prefix (e.g., `"NODE_1"`, `"NODE_2"`, ...)

NodeID is required — the dialog enforces that one option is selected and valid.

### PlotID Assignment Options

1. **No PlotID** — all features get empty string
2. **Existing field** — map a field from the input layer (source field is excluded from output)
3. **Auto-generate** — sequential integers with optional prefix

PlotID is optional.

## Geometry Requirements

- CRS: EPSG:4326
- Geometry type: Polygon or MultiPolygon (2D — no Z values)
- Coordinate precision: 6 decimal places (truncated)
- Valid polygon: must pass GEOS validity + TRACT geometry checks

## TRACTStatus Logic

A feature is `"READY"` if and only if it passes all checks:
- GEOS valid (or successfully repaired)
- No TRACT geometry errors (duplicates, degenerate rings, self-intersections)
- Area >= 0.05 ha
- No interior holes

If any check fails, the feature is `"NEEDS_FIX"` and all issues are listed in `TRACTIssue`.
