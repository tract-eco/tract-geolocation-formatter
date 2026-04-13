---
description: Create the directory structure for a new spec.
---

Create the directory structure for a new spec.

The argument is: `$ARGUMENTS`

## Instructions

1. Parse `$ARGUMENTS` for a ticket number and optional short description.
   - Accepted formats: `DEV-1234`, `DEV-1234 evidence attachments`, `DEV-1234-evidence-attachments`
   - If `$ARGUMENTS` is empty or does not contain a `DEV-\d+` pattern, ask for the ticket number and a short description.

2. Derive the directory name:
   - If a description was provided: `DEV-XXXX-slug` (lowercase, hyphenated)
   - If only a ticket number: `DEV-XXXX`

3. Check whether `.specify/specs/active/` already contains a directory starting with the ticket number. If it does, tell the user and stop.

4. Create the directory: `.specify/specs/active/{directory-name}/`

5. Create an `attachments/` subdirectory inside it with a `.gitignore` containing `*` (attachments are local reference material, not committed).

6. Tell the user:
   ```
   Created `.specify/specs/active/{directory-name}/`.
   Drop any reference material (user stories, scope, designs, requirements, product discovery docs, references ...) in the attachments/ directory, then run `/generate-spec {DEV-XXXX}`.
   ```
