---
description: Resume work on an active spec from a previous conversation.
---

Resume work on an active spec from a previous conversation.

The argument is: `$ARGUMENTS`

## Instructions

### Resolve target

1. Determine the target spec: use `$ARGUMENTS` if provided, or infer from context. Only ask the user if ambiguous.
2. If no active specs exist, tell the user and suggest `/start-spec`.

### Load context

3. Read all files in the spec directory (`spec.md`, `plan.md`, `tasks.md`, `decision-log.md`, `clarify.md`, and everything in `attachments/` — whichever exist).

### Determine phase

4. Determine the current phase based on which files exist and their state:
   - Only `spec.md` with unresolved questions in Open Questions or `clarify.md` → **clarify**
   - `spec.md` complete, no `plan.md` → **plan**
   - `plan.md` exists, no `tasks.md` → **tasks**
   - `tasks.md` exists with uncompleted tasks → **implement**
   - All tasks completed → **verify**

### Assess progress (if in implement phase)

5. Parse `tasks.md` for completion markers (checkboxes, dates).
6. Check git log for commits referencing the ticket number:
   ```bash
   git log --oneline --all --grep="DEV-XXXX" | head -20
   ```
7. Check for branches matching the ticket:
   ```bash
   git branch -a | grep -i "DEV-XXXX"
   ```
8. Cross-reference: which planned files already exist or have been modified?

### Health check

9. If in implement phase, run a quick test check:
   ```bash
   PYTHONPATH=src python -m pytest tests/ -x -q --tb=no 2>&1 | tail -5
   ```
   Report whether the test suite is green.

### Present status

10. Present a status report:

```
## Resume: DEV-XXXX — [Title]

**Phase:** [current phase]
**Branch:** [branch name if found, or "no branch yet"]
**Test suite:** [green / N failures / not checked]

### Progress
- Task 1: [title] — Done (YYYY-MM-DD)
- Task 2: [title] — Done (YYYY-MM-DD)
- Task 3: [title] — **Next up**
- Task 4: [title] — Blocked by Task 3

### Decision log
- DEC-1: [title] — [one-line summary]

### Open items
- [Any unresolved questions, flagged deviations, or issues]

### Suggested next step
[What to do next — e.g., "Run `/implement-task DEV-XXXX 3`" or "Resolve open question Q2 in clarify.md"]
```

11. Ask the user if they want to proceed with the suggested next step.

## Important

- This command is read-only — it never modifies spec files
- If the git history shows work not reflected in `tasks.md`, mention it
- If the spec has unresolved open questions, flag them prominently
