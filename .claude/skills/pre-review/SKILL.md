---
description: Review current branch code changes against the constitution and conventions before submitting for human review.
---

Review current branch code changes against the constitution and conventions before submitting for human review.

## Instructions

### Load rules

1. Read `.specify/constitutions/constitution.md`.
2. Read all files in `.specify/constitutions/conventions/`.
3. Read all files in `.specify/constitutions/domains/` that are relevant to the changed files (determine relevance from file paths and imports).

### Identify changes

4. Get all changed files on the current branch:
   ```bash
   git diff --name-only main...HEAD
   ```
5. Group changed files by layer (controller, service, repository, model, migration, test, pydantic model) based on file paths.

### Review

6. For each changed file, read it and check against every rule in the relevant convention file for that layer. Report each violation with:
   - File path and line number
   - The rule being violated (quote or reference the convention)
   - What the code does instead

7. Check cross-layer rules from `constitution.md` that span multiple files:
   - Import boundaries (e.g., controllers must not import ORM models)
   - Session management (who commits, who flushes, who rolls back)
   - Dependency injection patterns
   - Any other architectural rules defined in the constitution

### Report

8. Present findings grouped by file:

```
## Pre-review: [branch name]

### path/to/file.py
- **Line N:** [violation description] — rule: [quote from convention]
- **Line M:** [violation description] — rule: [quote from convention]

### path/to/other_file.py
- No violations

### Summary
- X files reviewed
- Y violations found
- Z files clean
```

9. If no violations found, say so and tell the user the branch is ready for human review.

## Important

- This is a read-only check — report violations, don't fix them
- Every reported violation must reference a specific rule from the constitution or conventions — no opinions
- If a convention file doesn't exist for a layer, skip that layer and note it
