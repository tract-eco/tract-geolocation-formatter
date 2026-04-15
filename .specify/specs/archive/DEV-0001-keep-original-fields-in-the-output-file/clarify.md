# Clarify: Keep Original Fields in the Output File

> **Ticket:** DEV-0001
> **Date:** 2026-04-14

Structured Q&A to resolve ambiguities from the spec before planning.

---

## Questions & Answers

### Q1: Should there be a UI toggle for including original fields?

**Context:** Currently the output always has 4 fixed fields. We could either always include original fields (simpler), or add a checkbox to the dialog letting the user choose. A toggle adds UI complexity but gives users control.

**Answer:** Always include original fields. No toggle needed.

**Decision:** No UI change. Original fields are always carried over to the output.

---

### Q2: How to handle input fields that clash with TRACT field names?

**Context:** If the input layer already has a field called `TRACTStatus` or `TRACTIssue`, the TRACT values would silently overwrite the original values. This could be confusing or cause data loss. Options: silently overwrite, warn the user, or prefix conflicting original fields (e.g., `orig_TRACTStatus`).

**Answer:** Keep the original field with a suffix, e.g., `NodeID_orig`. However, if the user selected that field to be used as NodeID or PlotID via "Use existing field", don't keep the original — the TRACT field already carries its value.

**Decision:** Conflicting fields get an `_orig` suffix, except when the field is the one mapped to NodeID/PlotID via "Use existing field" (in which case it is dropped since the value is already in the TRACT field).

---

### Q3: Keep or remove the field mapped to NodeID/PlotID?

**Context:** If the user maps an existing field `farm_id` to NodeID, the output would contain both `farm_id` (original) and `NodeID` (TRACT) with the same value. This is redundant but preserves the original schema. Removing `farm_id` would break the "keep all original fields" expectation.

**Answer:** Don't keep the original field when it's mapped via "Use existing field". The value is already in the TRACT field, so the duplicate is unnecessary.

**Decision:** When a field is selected as the source for NodeID or PlotID via "Use existing field", that field is excluded from the original fields in the output. Its value lives in the TRACT field.

---

## Out of scope

Items explicitly scoped out to a future spec or phase.

| Item | Reason | Revisit when |
|------|--------|-------------|
| UI toggle for original fields | Always include — no user choice needed | If users request TRACT-only export |

## Spec Updates

Changes made to `spec.md` as a result of clarification:

- [x] Updated functional requirements: original fields always included, no toggle
- [x] Added field clash handling: `_orig` suffix for conflicting names
- [x] Added mapped field exclusion: fields used as NodeID/PlotID source are dropped from original fields
- [x] Updated AC-2 and AC-3 to reflect mapped field exclusion
- [x] Added AC-7 for `_orig` suffix behavior
