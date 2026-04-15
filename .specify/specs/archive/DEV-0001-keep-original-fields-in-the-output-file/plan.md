# Plan: Keep Original Fields in the Output File

> **Ticket:** DEV-0001
> **Date:** 2026-04-14

Technical design for implementing the spec. All decisions must respect all files in `.specify/constitutions/**/**`.

---

## UI Changes

None.

## Processing Pipeline Changes

No changes to the geometry processing pipeline. The processing order (reproject → truncate → fix duplicates → makeValid → TRACT checks → area → holes) is unchanged.

The change is confined to two areas within `_run_transformation_from_dialog`:

1. **Output field construction** — build `out_fields` from input layer fields + TRACT fields
2. **Feature attribute writing** — copy original attribute values into each output feature

### New Helper: `_build_output_fields`

A new private method that encapsulates the field-building logic. This keeps `_run_transformation_from_dialog` clean and makes the field logic independently testable.

| Method | Input | Output | Purpose |
|--------|-------|--------|---------|
| `_build_output_fields(layer_fields, excluded_fields)` | `QgsFields` (input layer), `set[str]` (field names to exclude) | `tuple[QgsFields, dict[str, str]]` | Build output field list and return a rename map (`original_name → output_name`) for clashing fields |

**Logic:**

```python
TRACT_FIELD_NAMES = {"NodeID", "PlotID", "TRACTStatus", "TRACTIssue"}

def _build_output_fields(self, layer_fields, excluded_fields):
    out_fields = QgsFields()
    rename_map = {}  # original_name → output_name

    for field in layer_fields:
        name = field.name()

        # Skip fields mapped to NodeID/PlotID via "Use existing field"
        if name in excluded_fields:
            continue

        # Rename fields that clash with TRACT field names
        if name in TRACT_FIELD_NAMES:
            new_name = f"{name}_orig"
            rename_map[name] = new_name
            out_fields.append(QgsField(new_name, field.type()))
        else:
            out_fields.append(QgsField(name, field.type()))

    # Append TRACT fields
    out_fields.append(QgsField("NodeID", QVariant.String))
    out_fields.append(QgsField("PlotID", QVariant.String))
    out_fields.append(QgsField("TRACTStatus", QVariant.String))
    out_fields.append(QgsField("TRACTIssue", QVariant.String))

    return out_fields, rename_map
```

### Modified: `_run_transformation_from_dialog`

**Change 1: Build excluded fields set (after line 849, before out_fields)**

```python
excluded_fields = set()
if node_use_existing and node_field_name:
    excluded_fields.add(node_field_name)
if plot_existing and plot_field_name:
    excluded_fields.add(plot_field_name)
```

**Change 2: Replace out_fields construction (lines 920–925)**

Replace the 4-field hardcoded block with:

```python
out_fields, rename_map = self._build_output_fields(layer.fields(), excluded_fields)
```

**Change 3: Copy original attributes when writing features (lines 1331–1358)**

After `new_feat = QgsFeature(out_fields)`, before the NodeID/PlotID assignment block, add:

```python
# Copy original field values
for field in layer.fields():
    name = field.name()
    if name in excluded_fields:
        continue
    source_idx = layer.fields().indexFromName(name)
    val = f.attributes()[source_idx]
    output_name = rename_map.get(name, name)
    new_feat[output_name] = val
```

The existing NodeID/PlotID/TRACTStatus/TRACTIssue assignment code that follows remains unchanged — it overwrites the TRACT fields with the correct values.

## Output Changes

### GeoJSON Attribute Changes

| Field | Action | Type | Description |
|-------|--------|------|-------------|
| All input fields (except excluded) | Add | Preserved from input | Original attribute values carried over |
| Clashing fields | Rename | Preserved from input | Suffixed with `_orig` (e.g., `NodeID_orig`) |
| `NodeID` | Unchanged | String | TRACT NodeID — same behavior as before |
| `PlotID` | Unchanged | String | TRACT PlotID — same behavior as before |
| `TRACTStatus` | Unchanged | String | TRACT status — same behavior as before |
| `TRACTIssue` | Unchanged | String | TRACT issues — same behavior as before |

### Validation Report Changes

None.

## Component Structure

Files to create or modify:

### Plugin Logic
- [ ] `tract_geolocation_formatter/TRACT_Geolocation_Formatter.py`:
  - Add `TRACT_FIELD_NAMES` constant at module level (near existing constants, line ~67)
  - Add `_build_output_fields(self, layer_fields, excluded_fields)` method (in the helpers section, after `_get_ids`)
  - Modify `_run_transformation_from_dialog`: build `excluded_fields` set, replace `out_fields` construction, add original attribute copy loop

### Tests
- [ ] `tests/test_build_output_fields.py` — unit tests for `_build_output_fields`:
  - Basic case: input fields carried over, TRACT fields appended
  - Excluded fields: mapped NodeID/PlotID fields removed
  - Clash handling: input `NodeID` → `NodeID_orig`
  - Combined: exclusion + clash in same run

### Constitution / Docs
- [ ] `.specify/constitutions/constitution.md` — amend § 3 Output Contracts (per DEC-2)
- [ ] `.specify/constitutions/domains/tract-template.md` — update attribute table to reflect original fields

---

## Integration Points

Existing code to reuse or connect to:

| File / Method | What to reuse | How |
|---------------|--------------|-----|
| `TRACT_Geolocation_Formatter.py:780` | `layer.fields()` — already retrieved as `field_names` | Pass `layer.fields()` (QgsFields object) to `_build_output_fields` |
| `TRACT_Geolocation_Formatter.py:790-843` | `node_use_existing`, `node_field_name`, `plot_existing`, `plot_field_name` — already parsed from dialog | Use these to build `excluded_fields` set |
| `TRACT_Geolocation_Formatter.py:1331` | `QgsFeature(out_fields)` — feature construction | Same pattern, just with more fields now |
| `TRACT_Geolocation_Formatter.py:1335` | `f.attributes()` — reading source attributes | Reuse in the original-field copy loop |

## Risks & Considerations

- **GeoJSON field name length:** GeoJSON has no hard limit on property names, but Shapefile (if ever used as output) limits field names to 10 chars. Not a concern for GeoJSON output but worth noting if output format options are added later.
- **Field type preservation:** `QgsField.type()` returns `QVariant` types. GeoJSON supports String, Number, Boolean, and null. QGIS handles the mapping via `QgsVectorFileWriter` — no custom conversion needed.
- **Duplicate `_orig` collision:** theoretically an input could have both `NodeID` and `NodeID_orig`. This is an extreme edge case. The current plan does not handle recursive renaming — `NodeID_orig` would clash with the existing `NodeID_orig`. If this becomes a real concern, a follow-up spec can address it.
- **Performance:** copying attributes is O(fields × features). For 50 fields × 10,000 features = 500K attribute copies — negligible overhead vs. the geometry processing already happening per feature.
