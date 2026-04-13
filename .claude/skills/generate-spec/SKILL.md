---
description: Generate the spec for a feature ticket. Creates spec.md, clarify.md, and decision-log.md.
---

Generate the spec for `$ARGUMENTS`.

## Instructions

### Resolve target

1. Determine the target spec: use `$ARGUMENTS` if provided, or infer from context. Only ask the user if ambiguous.
2. Locate the spec directory in `.specify/specs/active/` matching the ticket number. If it does not exist, tell the user to run `/start-spec` first and stop.

### Load context

3. Read `.specify/constitutions/constitution.md`.
4. Scan `.specify/constitutions/domains/` and `.specify/constitutions/conventions/` — read file names and select only those relevant to the feature based on attachment content and description. Read selected files.
5. Read everything in the spec's `attachments/` directory (all file types: markdown, images, text).
6. Read the templates:
   - `.specify/templates/spec.md`
   - `.specify/templates/clarify.md`
   - `.specify/templates/decision-log.md`

### Generate

7. Generate `spec.md` in the spec directory using the template. Fill in all sections:
   - Description, success criteria, functional/non-functional requirements, constraints
   - Data model (DBML), API specification (OpenAPI 3.1), technical context, side effects, acceptance criteria
   - Acceptance criteria as concrete GIVEN/WHEN/THEN statements
   - Use the existing codebase to fill in Technical Context — search for relevant existing files, services, and patterns
   - Move attachment content into the appropriate spec sections — the spec should be self-contained

8. Generate `clarify.md` in the spec directory using the template. Populate with open questions discovered during spec generation:
   - Ambiguities in attachments or requirements
   - Missing information needed for technical design
   - Scope boundaries that need confirmation

9. Generate `decision-log.md` in the spec directory using the template. Record any early decisions made during generation (e.g., data model choices, scope interpretations).

### Clarification loop

10. Present the open questions from `clarify.md` to the user in chat.

11. As the user answers:
    - Write answers and resulting decisions into `clarify.md`
    - Update `spec.md` accordingly — track each change in the Changelog section
    - Items explicitly scoped out go to the "Out of scope" table in `clarify.md`
    - Record significant decisions in `decision-log.md`

12. Continue until all questions are resolved or scoped out.

13. Tell the user:
    ```
    Spec is ready for review. When confirmed, run `/generate-plan {DEV-XXXX}` to proceed to technical design.

    For epics or multi-story work: consider creating a dedicated spec review MR before moving to the plan phase.
    ```

## Important

- All specs must respect `.specify/constitutions/constitution.md` and relevant domain/convention files
- Acceptance criteria must be concrete enough to become pytest cases — if you can't picture the test, the AC is too vague
- Success criteria must be measurable (numbers, percentages, or binary conditions)
- Do not start technical design (plan.md) in this phase — that is `/generate-plan`
- The spec should be self-contained: a reader should not need to go back to attachments to understand the feature
