---
description: Generate the task breakdown for a feature ticket. Creates tasks.md with ordered, verifiable implementation steps.
---

Generate the task breakdown for `$ARGUMENTS`.

## Instructions

### Resolve target

1. Determine the target spec: use `$ARGUMENTS` if provided, or infer from context. Only ask the user if ambiguous.
2. Locate the spec directory in `.specify/specs/active/` matching the ticket number.
3. Read `spec.md` and `plan.md` in the spec directory. If `plan.md` does not exist, tell the user to run `/generate-plan` first and stop.

### Load context

4. Read the tasks template: `.specify/templates/tasks.md`.

### Generate

5. Create `tasks.md` in the spec directory using the template. Fill in:
   - Discrete, independently testable units (~1 MR each)
   - Each task includes:
     - **Description:** what the task does
     - **Depends on:** which tasks must be completed first
     - **Files:** paths to create/modify (from plan.md's Component Structure)
     - **Acceptance tests covered:** which AT-N from the spec this task satisfies
     - **Verification:** how to confirm the task is done (test command, lint command, manual check)
   - Order tasks by dependency (model before repository, repository before service, etc.)
   - Migration is NOT a task — it is user-generated via `alembic revision --autogenerate` after ORM model changes are complete. The task that creates/modifies ORM models must include a verification step instructing the user to run autogenerate.
   - Mark tasks that can run in parallel with `[P]`
   - Mark blocked tasks with `[B]`
   - Include a dependency graph at the bottom
   - Verify all acceptance tests from the spec are covered — list any uncovered ones in the "Uncovered Acceptance Tests" section

6. Tell the user:
    ```
    Tasks are ready. Review the breakdown, then start implementation with `/implement-task {DEV-XXXX} [task number]`.
    ```

## Important

- Only include tasks for this repo — cross-repo work belongs in plan.md's Cross-Repo Impact section
- Each task must be independently verifiable: after completing it, you should be able to run a test or check that proves it works
- Task granularity should match ~1 MR — not too granular (single file changes) and not too coarse (entire feature in one task)
- All acceptance tests from the spec must be assigned to at least one task
