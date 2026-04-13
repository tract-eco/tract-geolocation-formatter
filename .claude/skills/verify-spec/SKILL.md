---
description: Verify that the implementation matches the spec. Runs as part of /close-spec but also available ad hoc.
---

Verify that the implementation matches the spec. Runs as part of `/close-spec` but also available ad hoc.

The argument is: `$ARGUMENTS`

## Instructions

### Resolve target

1. Determine the target spec: use `$ARGUMENTS` if provided, or infer from context. Only ask the user if ambiguous.
2. Read all files in the spec directory (`spec.md`, `plan.md`, `tasks.md`, `decision-log.md`).

### Task completion check

3. Verify every task in `tasks.md` is marked as done. If any are incomplete, report them and ask the user whether to proceed or finish them first.

### Acceptance test coverage

4. For each acceptance criterion (AC-N) in `spec.md`:
   - Search test files listed in `plan.md` (and `tests/` broadly) for a corresponding pytest case
   - Match by: test name referencing the AC scenario, or test logic matching the GIVEN/WHEN/THEN
   - Report: `AC-N: [description] -> [test file:test name]` or `AC-N: [description] -> NOT FOUND`

### Plan vs reality diff

5. For each file listed in plan.md's Component Structure:
   - Check if the file exists on disk
   - If marked "Create" — verify it was created
   - If marked "Modify" — verify it was modified (`git diff main...HEAD -- [file]` or `git log --oneline -- [file]`)
   - Report files in the plan that don't exist or weren't touched
   - Report significant files changed but NOT listed in the plan (`git diff main...HEAD --name-only`)

### Decision log completeness

6. If plan deviations were found in step 5, check whether they're documented in `decision-log.md`. Flag undocumented deviations.

### Test suite health

7. Run the tests for files listed in the plan:
   ```bash
   PYTHONPATH=src python -m pytest [test files from plan] -v
   ```
   Report pass/fail.

8. Run linting on modified files:
   ```bash
   ruff check [modified files from plan]
   ```

### Constitution compliance

9. Read `.specify/constitutions/constitution.md` and relevant convention files from `.specify/constitutions/conventions/`.
10. For each file changed on the branch (`git diff --name-only main...HEAD`), check against the relevant convention rules. Report violations with file path, line number, and the rule being violated.

### Success criteria check

11. Present each success criterion from `spec.md` and ask the user to confirm:
   ```
   - [ ] Criterion 1 -> Met? (yes/no)
   - [ ] Criterion 2 -> Met? (yes/no)
   ```

### Report

12. Present a verification report:

```
## Verification Report: DEV-XXXX

### Tasks: X/X complete
### Acceptance Criteria: X/X covered by pytest cases
### Plan Files: X/X match (Y unplanned changes)
### Decision Log: X deviations documented, Y undocumented
### Tests: PASS/FAIL
### Lint: PASS/FAIL
### Constitution: X violations / Clean
### Success Criteria: X/X confirmed

**Verdict:** Ready to close / Needs attention
```

13. If there are discrepancies between the spec and the implementation, ask the user how to reconcile:
    - Is the spec correct (implementation needs fixing)?
    - Is the implementation correct (spec needs updating)?
    - Update the appropriate files based on the answer.

## Important

- This is primarily a validation phase — report issues, don't silently fix them
- Be specific about gaps: name the AC, the file, the deviation
- When run as part of `/close-spec`, the verdict determines whether archiving proceeds
