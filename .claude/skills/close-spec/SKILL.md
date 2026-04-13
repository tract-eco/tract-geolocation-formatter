---
description: Close a completed spec: verify implementation, then archive.
---

Close a completed spec: verify implementation, then archive.

The argument is: `$ARGUMENTS`

## Instructions

### Resolve target

1. Determine the target spec: use `$ARGUMENTS` if provided, or infer from context. Only ask the user if ambiguous.
2. Locate the spec directory in `.specify/specs/active/` matching the ticket number.

### Phase 1: Verify

3. Run the full `/verify-spec` process (see `verify-spec.md`):
   - Task completion check
   - Acceptance test coverage
   - Plan vs reality diff
   - Decision log completeness
   - Test suite health
   - Success criteria check

4. Present the verification report.

5. If the verdict is "Needs attention":
   - Ask the user how to reconcile each discrepancy (is the spec or implementation correct?)
   - Update the appropriate files based on the answers
   - Re-verify until clean, or until the user explicitly says to proceed anyway

### Phase 2: Archive

6. Confirm with the user that the spec is ready to archive.

7. Move the entire spec directory from `.specify/specs/active/` to `.specify/specs/archive/`.

8. Confirm the move was successful.

9. Tell the user:
    ```
    Spec DEV-XXXX archived. Create the implementation MR when ready.
    ```

## Important

- Never archive with a failing test suite without explicit user confirmation
- The verification phase is the same as `/verify-spec` — this skill just adds the archive step
- Archived specs retain all files (spec, plan, tasks, clarify, decision-log) for future reference
