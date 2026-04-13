---
description: Update an existing spec when requirements change.
---

Update an existing spec when requirements change.

The argument is: `$ARGUMENTS`

## Instructions

### Resolve target

1. Determine the target spec: use `$ARGUMENTS` if provided, or infer from context. Check both `.specify/specs/active/` and `.specify/specs/archive/`. Only ask the user if ambiguous.
2. Locate the spec directory. If found in `archive/`, move it to `active/` first.
3. Read all files in the spec directory (`spec.md`, `plan.md`, `tasks.md`, `decision-log.md`, `clarify.md` — whichever exist).

### Gather changes

4. Ask the user what changed and why:
   - New requirements?
   - Changed requirements?
   - Bug discovered that changes the design?
   - Scope reduction or expansion?

### Apply changes

5. Update `spec.md` with the changes (requirements, acceptance criteria, constraints, data model, API specification).
6. Track each change in the Changelog section of `spec.md`.
7. Update `plan.md` if the technical design is affected.
8. Update `tasks.md`:
   - Preserve completed tasks (don't re-order or modify done tasks)
   - Add new tasks or modify remaining ones as needed
   - Update dependency graph
9. Add a decision record to `decision-log.md` explaining what changed and why.

### Validate

10. Review the updated spec for completeness:
    - All acceptance criteria still have GIVEN/WHEN/THEN format
    - Success criteria still measurable
    - No unresolved open questions introduced
    - Constitution rules still respected

11. Present a summary of all changes made across files.

## Important

- Always record WHY the change was made in the decision log
- Don't delete old requirements — mark them as removed with strikethrough and a reason
- If the change invalidates completed work, flag it clearly to the user
