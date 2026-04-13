# v3 API Migration

Domain-specific rules for the v3 API standardization effort (DEV-6404). These rules
apply to all endpoints under `src/api/v3/`. They extend and, where noted,
override the general constitution and convention files.

v4 is reserved for net-new features that do not correspond to any legacy endpoint.
When `src/api/v4/` is created, these same rules apply.

**Companion docs:** `docs/DEV-6404/` contains the full reference material:
- `V3_STANDARDS.md` — canonical wire format specification (the single source of truth)
- `PR0_REFERENCE.md` — reference implementation patterns
- `MIGRATION_SPEC.md` — migration scope and approach
- `CHECKLIST.md` — endpoint migration tracker
- `TASKS.md` — task breakdown

---

## Core Principles

### Standards Compliance
Every v3 endpoint MUST comply with `V3_STANDARDS.md`. Any ambiguity is resolved by the standards document first, then by this domain file, then by team consensus recorded as an amendment.

### Incremental Adapter Migration
No big-bang rewrite. Legacy endpoints remain untouched until explicitly deprecated. New versioned routes are **additive** adapters that reuse existing services and repositories through thin orchestration layers.

### Domain Exceptions, Not Transport Exceptions
Services and repositories raise domain-specific `AppError` subclasses (defined in `src/common/api_contract/errors.py`):

| Exception | HTTP Status |
|-----------|-------------|
| `ValidationAppError` | 400 |
| `UnauthorizedAppError` | 401 |
| `ForbiddenAppError` | 403 |
| `NotFoundAppError` | 404 |
| `ConflictAppError` | 409 |
| `InternalAppError` | 500 |

They MUST NOT raise `HTTPException`. A global `ErrorMapper` (registered via `ErrorMapper.register(app)` in `app_factory.py`) serializes all `AppError` subclasses to RFC 63 Option B `errors[]` payloads.

> **Override:** The general convention files allow `HTTPException` in v2 controllers. For v3 work, all error signaling MUST use `AppError` subclasses instead.

### Typed Contracts Over Loose Dicts
Success responses use typed Pydantic models (`V3PagedResponse[T]`, `V3ObjectResponse[T]`). Error responses use typed response models (`ApiErrorsResponse`). No endpoint returns a raw `dict`.

**`Any` is prohibited as a generic type argument in `response_model` and handler return type annotations.** When wiring a v3 endpoint:
1. Identify the legacy endpoint being migrated (v0/v2 `response_model` or return type).
2. Use that exact model class as the type argument (e.g. `V3PagedResponse[Segment]`).
3. If no typed model exists, create one **before** wiring the endpoint.
4. `Any` MAY appear **only** as a temporary marker in a commit that also adds a `# TODO: define <ModelName>` comment and a corresponding task entry — it MUST be resolved before the endpoint is marked Completed in `CHECKLIST.md`.

---

## Wire Format

### Response Envelope
- Every v3 response MUST use `{ "data": ..., "meta": ... }`.
- `meta` MUST include `requestId`, `totalRowCount`, `pageSize`, and `offset` for list endpoints.
- Empty result sets return `200` with `data: []`. The `204` + JSON detail pattern is prohibited.
- Controllers MUST use `V3ObjectResponse[T]` or `V3PagedResponse[T]` — no domain-specific wrapper envelope classes.

### Request Body Envelope
- Mutating endpoints (POST, PUT, PATCH) MUST use `V3RequestBody[T]` with `{ "data": ..., "meta": ... }` shape.
- Domain attributes are flat under `data` — no JSON:API Resource Object nesting.
- GET and DELETE do not use request body envelopes.

### Error Format (RFC 63 Option B)
- All error responses MUST return a top-level `errors` array.
- Each error MUST contain: `status` (string), `code` (stable dot-namespaced `{domain}.{error_name}`), `title`, `detail`.
- Each error MAY contain: `source` (location of the error), `meta` (related key-value data including `requestId`).
- Internal details (stack traces, raw exception messages) MUST NOT leak. Generic 500 errors use a sanitized fallback payload.

### Naming
- **camelCase** for all JSON keys, Pydantic model fields (via alias generator), and Postgres columns.
- **PascalCase** for Python classes and database table names only.

### HTTP Verb Semantics
- **GET**: Read-only, safe, idempotent. Returns `200` with `{ data, meta }` (including empty `data: []`). `204 No Content` is NOT allowed for v3 data retrieval endpoints — it breaks envelope consistency.
- **POST**: Create a new resource, or execute a non-idempotent domain command.
- **PUT**: Full replacement of a target resource. MUST be idempotent.
- **PATCH**: Partial update. For collection PATCH, all-or-nothing semantics apply (not partial failure).
- **DELETE**: Remove a resource. SHOULD be idempotent from the client perspective.
- **Method override prohibition**: Domain actions MUST NOT be tunneled through incorrect verbs (e.g. no state-changing behavior on GET).

---

## Pagination & Query Parameters

- `page[limit]` and `page[offset]` (not bare `pageSize`/`offset` query params).
- `filter[...]` for filtering, `sort` for sorting.

### Composable Query Parameter DTOs

| DTO | Responsibility | Injection |
|-----|---------------|-----------|
| `V3JSONAPIFilterParams` (`src/common/custom_page.py`) | `page[limit]`, `page[offset]` | Automatic via `V3PagedResponse.__params_type__` |
| `V3SortParams` (`src/common/api_contract/params.py`) | `sort` | Explicit `Depends()` |
| Domain filter DTO | `filter[field]` values | Explicit `Depends()` |

- Pagination MUST NOT appear in the controller signature.
- Controllers MUST NOT declare individual `Query(...)` parameters for filter fields — all `filter[...]` params go in the domain filter DTO.
- Filter DTOs are **plain classes** (not `BaseModel`) with `Query(alias="filter[...]")` in `__init__`.
- Naming: `<Domain>FilterParams` in `src/models/<domain>_filters.py`.
- `V3SortParams` is a shared DTO in `src/common/api_contract/params.py`; it MUST NOT be duplicated per domain.
- Filter DTOs SHOULD implement `to_applied_filters(self) -> dict[str, Any]` returning a camelCase dict of non-`None` active filter values. Required only when the endpoint opts in to populating `meta.appliedFilters`; endpoints that do not echo filters may omit it.

---

## Controller Overrides (v3 only)

These override the general `conventions/controllers.md` for v3 endpoints:

- All handlers MUST be `async def`.
- Controllers MUST NOT call repositories directly (no trivial-operation exception).
- Controllers MUST NOT encode role-based domain policy (`if ROLE in ...` branching). Pass principal context to the service; ownership checks and conditional rules by role belong in the service and MUST surface failures via `AppError` subclasses.
- Controllers MUST NOT catch domain exceptions — that is `ErrorMapper`'s job.
- Controllers MUST NOT import or forward ORM query objects.
- Services and facades return domain-typed results; the controller maps them into wire envelopes.
- Controllers MUST use `V3RequestBody[T]` on the parameter for mutating endpoints.
- Controllers declare sort, filter DTOs via `Depends()`; pagination is implicit via `V3PagedResponse.__params_type__`.
- A controller's body should be limited to: extracting `requestId`, calling the injected service, and returning the typed response.

### Dependency Injection
- Every new service (including facades) MUST be injected via `Depends(get_<domain>_service)`.
- Provider function declares upstream dependencies and returns the constructed instance.
- Controllers declare: `service: FooService = Depends(get_foo_service)`.
- Services MUST NOT be constructed inline inside controller function bodies.

---

## Quality Requirements

- Every v3 endpoint MUST have contract tests covering success envelope shape (`{ data, meta }`), request body envelope shape (`{ data, meta? }`) for mutating endpoints, and error payload shape (`{ errors: [...] }`).
- Every new error `code` MUST have exception mapping coverage.
- Existing tests for non-migrated endpoints MUST continue to pass (backward compatibility).
- OpenAPI specs MUST be exported and linted with Spectral when the API surface changes. Spectral validates path/structure rules but does NOT validate response body shapes — contract tests and code review cover payload correctness.

---

## Boundaries

- Public endpoints are excluded from v3 standardization.
- Sparse fieldsets (`fields[...]`) are not supported.
- PostgreSQL table redesign is out of scope; existing schemas are reused as-is.

---

## Governance

- **Standards authority**: `V3_STANDARDS.md` is the canonical reference. This domain file interprets and operationalizes it.
- **Amendments**: any change to this file requires team review and explicit approval. Changes are recorded in the amendment log.
- **Enforcement**: PRs introducing v3 endpoints MUST reference this domain file. Code review checks compliance.

---

**Version**: 2.8 | **Ratified**: 2026-03-25 | **Last Amended**: 2026-04-02

### Amendment log

| Version | Date | Change |
|---------|------|--------|
| 2.8 | 2026-04-01 | Relaxed `to_applied_filters()` from MUST to SHOULD. |
| 2.7 | 2026-04-01 | Added `Any`-prohibition rule for generic type arguments. |
| 2.6 | 2026-03-31 | Hardened filter DTO binding rules; added naming/file conventions. |
