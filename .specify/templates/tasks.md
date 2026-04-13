# Tasks: [Title]

> **Ticket:** DEV-XXXX
> **Date:** YYYY-MM-DD

Discrete, independently testable units. Each task targets ~1 MR.

---

## Legend

- `[P]` — Can run in parallel with other `[P]` tasks at the same level
- `[B]` — Blocked by the task(s) listed in "Depends on"
- **AT-N** — References acceptance test N from the spec

## Task Breakdown

### Task 1: [Title]

- **Description:** [What this task does]
- **Depends on:** None
- **Files:**
  - Create: `path/to/new_file.py`
  - Modify: `path/to/existing_file.py`
- **Acceptance tests covered:** AT-1
- **Verification:** [How to confirm this task is done — test command, manual check, etc.]

---

### Task 2: [Title] `[P]`

- **Description:**
- **Depends on:** Task 1
- **Files:**
  - Create:
  - Modify:
- **Acceptance tests covered:**
- **Verification:**

---

### Task 3: [Title] `[P]`

- **Description:**
- **Depends on:** Task 1
- **Files:**
  - Create:
  - Modify:
- **Acceptance tests covered:**
- **Verification:**

---

### Task 4: [Title] `[B]`

- **Description:**
- **Depends on:** Task 2, Task 3
- **Files:**
  - Create:
  - Modify:
- **Acceptance tests covered:**
- **Verification:**

## Dependency Graph

```
Task 1
├── Task 2 [P]
├── Task 3 [P]
└── Task 4 [B] (after 2 + 3)
```

## Uncovered Acceptance Tests

List any acceptance tests from the spec not yet assigned to a task:

- None (all covered)
