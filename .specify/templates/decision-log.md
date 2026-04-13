# Decision Log: [Title]

> **Ticket:** DEV-XXXX

Records key design decisions and their rationale. Useful when revisiting the spec later.

---

## DEC-1: [Short decision title]

**Date:** YYYY-MM-DD
**Status:** accepted | superseded | reverted

**Context:** [What situation or constraint prompted this decision]

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| A: [description] | | |
| B: [description] | | |

**Decision:** [Which option was chosen]

**Rationale:** [Why — the reasoning that tipped the balance]

**Consequences:** [What this means for the implementation, what trade-offs we accept]

---

<!-- EXAMPLE (delete this section when using the template)

## DEC-1: Store notes as plain text, not markdown

**Date:** 2026-03-15
**Status:** accepted

**Context:** Supplier notes need a text format. The frontend currently has no markdown renderer, and notes are short free-text comments, not structured documents.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| A: Plain text | Simple, no rendering needed, consistent display | No formatting, links not clickable |
| B: Markdown | Rich formatting, future-proof | Needs frontend renderer, XSS risk if not sanitized, overkill for short notes |

**Decision:** Plain text (Option A)

**Rationale:** Notes are short comments (max 2000 chars), not documents. Adding a markdown renderer and sanitizer is complexity we don't need. If we want formatting later, we can migrate — plain text is valid markdown.

**Consequences:** Frontend displays notes as-is in a `<pre>` or `<p>` tag. No sanitization needed beyond standard input validation. URLs in notes won't be clickable.

## DEC-2: Skip service layer for note listing

**Date:** 2026-03-15
**Status:** accepted

**Context:** The GET /suppliers/{id}/notes endpoint is a simple passthrough — filter by supplier_id, paginate, return. No business logic involved.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| A: Controller → Service → Repository | Consistent with other endpoints | Empty service method, adds a file with no logic |
| B: Controller → Repository directly | Less boilerplate, constitution allows it for trivial reads | Slightly inconsistent, need to add service later if logic grows |

**Decision:** Controller → Repository directly (Option B)

**Rationale:** Constitution explicitly allows skipping the service layer for "simple passthrough reads with no business logic." The list endpoint is exactly that — filter + paginate. Create/update endpoints still go through the service since they have validation logic.

**Consequences:** If we later add logic to listing (e.g., filtering by note author permissions), we'll need to introduce a service method then. Acceptable trade-off.

END EXAMPLE -->
