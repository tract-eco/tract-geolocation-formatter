# Decision Log: Check minimum area on individual polygon parts

> **Ticket:** GH-2

Records key design decisions and their rationale. Useful when revisiting the spec later.

---

## DEC-1: Keep the whole-geometry area check alongside per-part check

**Date:** 2026-04-15
**Status:** accepted

**Context:** We could replace the existing whole-geometry area check with a per-part check, or keep both. For simple polygons, the whole-geometry check is sufficient. For multipolygons, per-part is needed.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| A: Replace whole-geometry with per-part only | Simpler, one check | Changes behavior for simple polygons (now reported as "part 1" instead of whole geometry) |
| B: Keep both, add per-part for multipolygons | No behavior change for simple polygons, clear separation of issue types | Two checks, two issue types |

**Decision:** Option B — keep both

**Rationale:** The existing `small_area` check is well-established. Adding `small_area_part` alongside it keeps backward compatibility and makes the validation report clearer — users can distinguish between "the whole feature is too small" and "one part within the feature is too small."

**Consequences:** Two issue types in the validation report: `small_area` (whole geometry) and `small_area_part` (individual part). A multipolygon where the total is below threshold will get both.

---

## DEC-2: Inline the per-part check instead of extracting a helper method

**Date:** 2026-04-15
**Status:** accepted

**Context:** The per-part area check could be a standalone helper method or inline code in the main loop.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| A: Extract to `_check_part_areas` helper | Testable in isolation, consistent with other helpers | Overkill for a single-use ~20 line block, adds a method to an already large class |
| B: Inline after existing area check | Simple, follows the same pattern as the surrounding code, easy to read in context | Slightly harder to unit test in isolation |

**Decision:** Option B — inline

**Rationale:** The logic is a straightforward loop using the same pattern as the existing area check and holes detection. It doesn't benefit from extraction since it's tightly coupled to the local variables (`area_transform`, `feature_status`, `feature_issues`, `validation_rows`). If the area check logic grows further in the future, extraction can happen then.

---

## DEC-3: Guard per-part check with `len(multipoly) > 1`

**Date:** 2026-04-15
**Status:** accepted

**Context:** During e2e validation, single polygons stored as MultiPolygon with one part were incorrectly triggering the per-part check, producing duplicate `small_area` + `small_area_part` rows. Many GIS formats store single polygons as MultiPolygon with one part, so `geom.isMultipart()` alone is insufficient.

**Decision:** Added `if len(multipoly) > 1:` guard so the per-part check only runs when there are genuinely multiple parts.

**Consequences:** Single-part multipolygons are treated the same as simple polygons — covered by the whole-geometry check only.

---

## DEC-4: Separate `small_area_part_features` list for the summary report

**Date:** 2026-04-15
**Status:** accepted

**Context:** During e2e validation, per-part area failures did not appear in the pop-up summary report. Initially they were appended to `small_area_features`, which mixed whole-geometry and per-part failures with no distinction.

**Decision:** Created a dedicated `small_area_part_features` list (stores `(fid, part_idx, area)`) and a separate section in the summary report: "Polygon parts below minimum area" with messages like "Feature 7, part 2: 0.0085 ha".

**Consequences:** The summary report now clearly distinguishes between whole-polygon area issues and per-part area issues.
