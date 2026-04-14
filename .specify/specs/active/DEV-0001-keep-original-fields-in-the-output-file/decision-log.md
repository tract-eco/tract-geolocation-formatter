# Decision Log: Keep Original Fields in the Output File

> **Ticket:** DEV-0001

Records key design decisions and their rationale. Useful when revisiting the spec later.

---

## DEC-1: Conflicting field names get `_orig` suffix

**Date:** 2026-04-14
**Status:** accepted

**Context:** The input layer may contain fields with names that collide with TRACT output fields (`NodeID`, `PlotID`, `TRACTStatus`, `TRACTIssue`). We need to decide how to handle this.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| A: Silently overwrite | Simple, no extra logic | User may lose original values without knowing |
| B: Warn the user via dialog before export | User is informed, can rename fields first | Adds UI logic, may block workflow unnecessarily |
| C: Suffix conflicting original fields (e.g., `NodeID_orig`) | No data loss, no user action needed | Output schema includes suffixed fields |

**Decision:** Option C — suffix with `_orig`

**Rationale:** Preserves original data without user intervention. The `_orig` suffix is clear and unambiguous. Exception: if the conflicting field is the one the user selected as NodeID/PlotID source via "Use existing field", it is dropped entirely (its value is already in the TRACT field, so the `_orig` copy would be redundant).

**Consequences:** Output may contain fields like `NodeID_orig` if the input had a `NodeID` field that wasn't selected as the NodeID source. Code must check for name collisions when building `out_fields`.

---

## DEC-2: Constitutional amendment to Output Contracts

**Date:** 2026-04-14
**Status:** accepted

**Context:** Constitution § 3 (Output Contracts) currently states: "GeoJSON output must contain exactly four attributes: NodeID, PlotID, TRACTStatus, TRACTIssue. Do not add or remove attributes without updating the TRACT template specification." This spec requires changing that rule.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| A: Amend the rule to allow original fields alongside TRACT fields | Enables the feature, still guarantees TRACT fields are present | Broader output contract, consumers must handle variable schemas |
| B: Keep the rule and don't implement this feature | No change needed | Users lose context when working with output files |

**Decision:** Option A — amend the rule

**Rationale:** The four TRACT fields remain guaranteed. The additional original fields are a superset that doesn't break any downstream consumer expecting those four fields. The TRACT platform ingestion should ignore unknown fields.

**Consequences:** Constitution § 3 will be updated to: "GeoJSON output must contain at minimum the four TRACT attributes. Original input fields are preserved alongside them." Domain file `tract-template.md` must also be updated.

---

## DEC-3: Mapped fields are excluded from original fields

**Date:** 2026-04-14
**Status:** accepted

**Context:** When the user selects "Use existing field" for NodeID or PlotID, the selected field's value is copied into the TRACT field. Should the original field also appear in the output?

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| A: Keep the original field (duplicate value) | Complete preservation of input schema | Redundant data, confusing to see same value twice |
| B: Drop the mapped field | Clean output, no redundancy | Original schema not fully preserved |

**Decision:** Option B — drop the mapped field

**Rationale:** The value is already present in the TRACT field. Keeping a duplicate under the original name adds confusion without value. Users who selected the field as NodeID/PlotID already understand it maps to the TRACT field.

**Consequences:** The field exclusion only applies to "Use existing field" mode. In "Same value" or "Auto-generate" modes, all original fields are kept (they aren't mapped from an input field).

---

## DEC-4: Extract `_build_output_fields` as a separate helper method

**Date:** 2026-04-14
**Status:** accepted

**Context:** The field construction logic (exclusion, renaming, appending TRACT fields) could live inline in `_run_transformation_from_dialog` or be extracted into a dedicated method.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| A: Inline in `_run_transformation_from_dialog` | Less indirection | Method already ~500 lines, harder to test field logic in isolation |
| B: Extract to `_build_output_fields` helper | Testable, keeps main method cleaner, returns rename_map for use later | One more method on the class |

**Decision:** Option B — extract to `_build_output_fields`

**Rationale:** The main transformation method is already long. The field construction logic has clear inputs (layer fields, excluded set) and outputs (QgsFields, rename map), making it a natural extraction target. It can be unit tested without QGIS dialog/project dependencies.

**Consequences:** New method `_build_output_fields(self, layer_fields, excluded_fields)` returns `(QgsFields, dict)`. The rename map is needed downstream when copying attribute values.
