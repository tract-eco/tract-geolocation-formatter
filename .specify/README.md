# Spec-Driven Development (SDD)

## Flow

```
/start-spec DEV-XXXX short description
    -> Manual: drop reference materials in attachments/
/generate-spec DEV-XXXX
    -> Clarification loop in chat
    -> Spec complete
/generate-plan DEV-XXXX
    -> Technical design
/generate-tasks DEV-XXXX
    -> Task breakdown
/implement-task DEV-XXXX [task number]
    -> Repeat per task
/pre-review
    -> Convention check before MR
/close-spec DEV-XXXX
    -> Verify + archive
```

Ad hoc: `/verify-spec`, `/update-spec`, `/resume-spec`

## Two Workflows

### Epic / Multi-Story (Kick-off Lab / Objective Flow)

For large features spanning multiple stories or requiring cross-team alignment.

1. **Spec MR** (dedicated) — review `spec.md` and technically align before any implementation
2. **Implementation MR** (dedicated) — code + archived spec for reviewer context

### Single Story / Simple Task (Task Flow)

For straightforward work within established patterns.

1. **One MR** — spec and implementation together
2. Flexible on which spec artifacts to include — use what adds value, skip what doesn't

## What Gets Committed

### Spec Review MR (epics only)

```
.specify/specs/active/DEV-XXXX/
    attachments/          # .gitignore'd — not committed
    spec.md               # Review this
    clarify.md            # Context, no review needed
    decision-log.md       # Context, no review needed
```

### Implementation MR

```
.specify/specs/archive/DEV-XXXX/
    spec.md               # Review if changed since spec MR
    clarify.md            # No review needed
    decision-log.md       # No review needed
    plan.md               # No review needed
    tasks.md              # No review needed
src/...                   # Review as normal
tests/...                 # Review as normal
```

## Personal Flexibility

- You can play around and amend anything in `.specify/` and keep it uncommitted.
- Amendments pushed for the entire team need a dedicated MR.

## Structure

```
.specify/
    constitutions/
        constitution.md           # Global rules
        domains/                  # Domain-specific rules
        conventions/              # Layer-specific code patterns
    templates/                    # Templates for spec artifacts
    specs/
        active/                   # In-progress specs
        archive/                  # Completed specs
```

## When to Use SDD

| Scope | Approach |
|-------|----------|
| **Epic / multi-story** | Full flow with dedicated spec MR |
| **Single story** | Full or partial flow, one MR |
| **Small change** (1-3 files, established pattern) | Lightweight — use what helps, skip what doesn't |
| **Bug fix, dep update, config** | Just do it |
