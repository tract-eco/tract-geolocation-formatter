# Clarify: Check minimum area on individual polygon parts

> **Ticket:** GH-2
> **Date:** 2026-04-15

Structured Q&A to resolve ambiguities from the spec before planning.

---

## Questions & Answers

### Q1: Part indexing — 1-based or 0-based?

**Context:** The validation report message will say something like "Polygon part N area below minimum." The summary report dialog already uses 1-based indexing for features (Feature 1, Feature 2, ...). Using 1-based for parts would be consistent for the user.

**Answer:** 1-based. Consistent with the existing feature indexing in the report.

**Decision:** Use 1-based indexing for polygon parts in validation messages (e.g., "Polygon part 1", "Polygon part 2").

---

### Q2: Skip per-part check for simple polygons?

**Context:** For a simple (non-multi) polygon, there is only one "part" — the whole geometry. The existing whole-geometry check already covers this case. Running the per-part check would be redundant and produce a duplicate validation row. The spec proposes skipping it for simple polygons.

**Answer:** Yes, skip for simple polygons.

**Decision:** Per-part area check only runs for multipolygon geometries. Simple polygons are covered by the existing whole-geometry check.

---

## Out of scope

Items explicitly scoped out to a future spec or phase.

| Item | Reason | Revisit when |
|------|--------|-------------|
| | | |

## Spec Updates

Changes made to `spec.md` as a result of clarification:

- [x] Confirmed 1-based part indexing in AC messages
- [x] Confirmed per-part check skipped for simple polygons (AC-4 unchanged)
