---
description: Generate the technical plan for a feature ticket. Creates plan.md with DB changes, API design, and component structure.
---

Generate the technical plan for `$ARGUMENTS`.

## Instructions

### Resolve target

1. Determine the target spec: use `$ARGUMENTS` if provided, or infer from context. Only ask the user if ambiguous.
2. Locate the spec directory in `.specify/specs/active/` matching the ticket number.
3. Read `spec.md` and `clarify.md` in the spec directory.
4. Verify the spec has no unresolved open questions. If it does, ask the user to resolve them first or run `/generate-spec` to continue the clarification loop.

### Load context

5. Read `.specify/constitutions/constitution.md`.
6. Scan `.specify/constitutions/domains/` and `.specify/constitutions/conventions/` — read files relevant to this spec's domain and affected layers.
7. Read the plan template: `.specify/templates/plan.md`.

### Codebase exploration

8. Before writing the plan, search the codebase for a similar existing feature to use as a reference implementation:
   - Grep for keywords from the spec in controller, service, and repository directories
   - Find an entity that shares traits (similar DB structure, endpoint pattern, cross-repo interaction)
   - Note the reference implementation in the plan's "Integration Points" section

### Generate

9. Create `plan.md` in the spec directory using the template. Fill in all sections:
   - **Database changes:** New tables, modified tables, indexes. Column types, constraints, rationale.
   - **API design:** Endpoint paths, methods, auth, request/response shapes, error cases. Must conform to the spec's OpenAPI definition.
   - **Component structure:** Files to create/modify, organized by layer (migration, ORM model, repository, service, pydantic models, controller, tests).
   - **Seed data:** If the spec requires reference/catalog data. Remove section if not applicable.
   - **Integration points:** Existing code to reuse, with file paths and method names.
   - **Cross-repo impact:** Contracts for other teams (payload shapes, shared schemas, expected behavior). Enough detail for independent implementation.

10. Update `decision-log.md` with any technical decisions made during planning (e.g., index strategy, seed data approach, cross-repo contract design).

11. Tell the user:
    ```
    Plan is ready for review. When confirmed, run `/generate-tasks {DEV-XXXX}` to break it into implementable tasks.
    ```

## Important

- The plan must respect all constitution rules, domain guides, and conventions
- Component structure must follow the layered architecture: model -> repository -> service -> pydantic models -> controller -> tests. Migration is listed but user-generated (see plan template).
- Reference specific files and functions to reuse — don't leave Integration Points vague
- Cross-repo work is documented as contracts/handoffs, not as implementation tasks for this repo
- Do not generate tasks in this phase — that is `/generate-tasks`
