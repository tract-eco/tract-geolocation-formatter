---
description: Implement a task from an active spec's task breakdown.
---

Implement a task from an active spec's task breakdown.

The argument is: `$ARGUMENTS`

## Instructions

### Resolve target

1. Determine the target spec: use `$ARGUMENTS` if provided, or infer from context. Only ask the user if ambiguous.
2. Locate the spec directory in `.specify/specs/active/` matching the ticket number.
3. Read `spec.md`, `plan.md`, and `tasks.md` in the spec directory.
4. If `$ARGUMENTS` contains a task number, use it. Otherwise:
   - If a task number was not provided: find the next uncompleted task in dependency order and confirm with the user.
   - If no task number and user wants all tasks: implement all tasks in sequence.

### Load context

5. Read `.specify/constitutions/constitution.md`.
6. Scan `.specify/constitutions/conventions/` — read the convention files relevant to the layers this task touches (e.g., `controllers.md` for controller work, `services.md` for service work).
7. Scan `.specify/constitutions/domains/` — read only files listed in the spec's Technical Context "Domain guides" field.

### Pre-flight checks

8. **Verify dependencies are done** — don't just check the checkbox in `tasks.md`:
   - For each dependency task, verify its key output files exist on disk
   - If a dependency's files are missing, warn the user: "Task N is marked done but [file] doesn't exist — was it implemented on a different branch?"

9. **Verify green baseline** — run existing tests to confirm you're not building on a broken foundation:
   ```bash
   PYTHONPATH=src python -m pytest tests/ -x -q --tb=short 2>&1 | tail -10
   ```
   If tests fail, report and ask the user whether to proceed or fix first. Do NOT silently continue.

### Implementation

10. Implement the task:
    - Follow the file paths and structure from `plan.md` exactly
    - Follow the code patterns from the convention files read in step 6
    - Map acceptance tests from the spec to concrete test cases

11. Write tests:
    - Follow conventions from `.specify/constitutions/conventions/` (e.g., testing conventions)
    - Cover happy path, error cases, and auth for controller endpoints
    - Cover business logic and exceptions for services

### Post-flight checks

12. **Run tests:**
    - Run new test files: `PYTHONPATH=src python -m pytest tests/path/to/new_test.py -v`
    - Re-run dependency task test files to check for regressions
    - Fix any failures before marking done

13. **Run linting:**
    - `ruff check --fix [files you created or modified]`
    - `ruff format [files you created or modified]`
    - Do NOT run ruff on files you didn't touch

14. **Check for unplanned changes:**
    - Run `git diff --name-only` and compare against the task's "Files" list in `tasks.md`
    - Trivial additions (e.g., `__init__.py` imports) are fine — note them
    - Significant deviations: ask the user and record in `decision-log.md`

15. **Update spec artifacts:**
    - Mark the task as completed with the date in `tasks.md`: `- [x] (YYYY-MM-DD)`
    - If anything didn't match the plan, add a decision record to `decision-log.md` with the rationale

16. Tell the user what was implemented, note any deviations, and suggest the next task.

## Important

- **Do not run Alembic commands.** Migrations require a live database connection that you do not have. When a task involves ORM model changes: create/modify the model, register new models in `src/sqlalchemy_pg/__init__.py`, then instruct the user to run `alembic revision --autogenerate -m "slug"` and review the generated migration before committing.
- Follow the plan — don't deviate from the agreed design without discussing with the user
- Don't implement tasks out of dependency order unless the user explicitly asks
- Run tests and linting before declaring a task done
- Pre-flight failures are warnings, not blockers — the user decides whether to proceed
