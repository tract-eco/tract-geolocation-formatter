# Spec: [Title]

| Field  | Value      |
|--------|------------|
| Ticket | DEV-XXX    |
| Author |            |
| Date   | YYYY-MM-DD |

---

## Description

<!-- Guidelines:
- One paragraph describing what this spec does and why
-->


## Success Criteria

<!-- Guidelines:
- Each criterion must be measurable and verifiable
-->

- [ ] Criterion 1 (measurable)
- [ ] Criterion 2 (measurable)


## Functional Requirements

<!-- Guidelines:
- Non-trivial requirements only. Omit section if none
-->

## Non-Functional Requirements

<!-- Guidelines:
- Non-trivial requirements only. Omit section if none
-->


## Constraints (DO NOT)

<!-- Guidelines:
- Explicit boundaries: things this spec must NOT do
- Must reference constitution rules where applicable
-->

- Must follow constitution rules (see all files in `.specify/constitutions/**/**`)
- DO NOT [explicit constraint]

---

## UI Changes

<!-- Guidelines:
- Describe any changes to the plugin dialog (.ui file)
- New controls, modified labels, layout changes
- Include mockup or description of user interaction flow
- Omit section if no UI changes
-->

## Processing Pipeline Changes

<!-- Guidelines:
- Describe changes to the geometry processing pipeline
- Specify where in the pipeline order the change applies (see constitution § 2)
- New checks, new repairs, modified validation logic
- Omit section if no pipeline changes
-->

## Output Changes

<!-- Guidelines:
- Changes to the GeoJSON output schema (new/modified attributes)
- Changes to the validation report (new issue types, new columns)
- Changes to the summary report dialog
- Omit section if no output changes
-->


## Technical Context

<!-- Guidelines:
- Affected areas: UI / geometry helpers / pipeline / output / tests
- Existing code to reuse: list specific methods if known
- Dependencies: any new QGIS API usage or external libraries
-->


## Acceptance Criteria

<!-- Guidelines:
- One AC per observable behavior
- Cover: happy path, edge cases (empty geometry, multipolygon, mixed types), error cases
- Each AC becomes a test case during implementation — if you can't picture the test, the AC is too vague
-->

1. **AC-1:** GIVEN [precondition], WHEN [action], THEN [expected result]
2. **AC-2:** GIVEN [precondition], WHEN [action], THEN [expected result]


## Open Questions

<!-- Guidelines:
- Questions that need clarification before planning
- Remove or move to clarify.md once resolved
-->

- [ ] [Question that needs clarification before planning]


## Changelog

<!-- Guidelines:
- Record spec changes, not implementation changes
- Each row = one meaningful revision
-->

| Date       | Author | Change        |
|------------|--------|---------------|
| YYYY-MM-DD |        | Initial draft |
