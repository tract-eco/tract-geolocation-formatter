# Plan: [Title]

> **Ticket:** DEV-XXXX
> **Date:** YYYY-MM-DD

Technical design for implementing the spec. All decisions must respect all files in `.specify/constitutions/**/**`.

---

## Database Changes

### New Tables

```
table_name
├── id           UUID PK (gen_random_uuid)  -- from Base
├── column_name  TYPE [NOT NULL | NULLABLE]
├── created_at   DateTime                    -- from Base
└── updated_at   DateTime                    -- from Base
```

### Modified Tables

| Table | Change | Migration notes |
|-------|--------|----------------|
| | | |

### Indexes

| Table | Columns | Type | Rationale |
|-------|---------|------|-----------|
| | | | |

## API Design

### Endpoints

#### `METHOD /api/v2/resource-name`

**Auth:** [Role required]
**Response wrapper:** `JSONAPIResponse[T]` | `JSONAPIFilterPage[T]`

**Request:**
```json
{}
```

**Response:** `STATUS_CODE`
```json
{
  "data": [],
  "meta": {}
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | |
| 401 | |
| 403 | |
| 404 | |

## Component Structure

Files to create or modify, organized by layer (bottom-up):

### Migration
- [ ] `alembic/versions/YYYY_MM_DD_HHMM-{rev}_slug.py` — **user-generated** via `alembic revision --autogenerate -m "slug"` after ORM model changes are complete and registered in `src/sqlalchemy_pg/__init__.py`

### ORM Model
- [ ] `src/sqlalchemy_pg/models/new_model.py`

### Repository
- [ ] `src/sqlalchemy_pg/repositories/new_repository.py` (extend `BaseRepository` from `src/sqlalchemy_pg/base/base_repository.py`)

### Service
- [ ] `src/services/new_service.py`

### Pydantic Models
- [ ] `src/models/new_model.py`

### Controller
- [ ] `src/api/v2/controllers/new_controller.py`

### Tests
- [ ] `tests/api/v2/controllers/test_new_controller.py`
- [ ] `tests/services/test_new_service.py`

## Seed Data

<!--
Include this section if the spec requires initial/reference data (catalogs, lookup tables, default settings).
Remove this section if not applicable.
-->

Write "None" if no seed data is needed.

Otherwise, document:

### Seed: `table_name`

**Method:** `alembic migration INSERT` | `alembic/seeds/*.sql` | `manual after deploy`

**Data:**

| Column | Value | Notes |
|--------|-------|-------|
| | | |

**When to run:** During migration (automatic) / After deploy (manual) / Via seed runner (`alembic/seeds/`)

**Idempotency:** How to handle re-runs — INSERT with ON CONFLICT? Check-before-insert? Seed runner SHA tracking?

---

## Integration Points

Existing code to reuse or connect to:

| File | What to reuse | How |
|------|--------------|-----|
| | | |

## Cross-Repo Impact

Write "None" if this spec is fully contained in traceability.

Otherwise, document each handoff as a **contract** — enough detail for the other team to implement independently.

### Contract: data (DAG: `dag_id_here`)

**Trigger:** How traceability initiates this (DAG trigger, PubSub, shared table)
```python
# Example: trigger_dag("dag_id", data={"key": "value"})
```

**Payload / shared table schema:**
```
table_or_payload_name
├── field_name   TYPE   -- description
└── field_name   TYPE   -- description
```

**Expected behavior:**
- What the DAG should do with the data
- What state this repo assumes after the DAG runs

**Blocking?** Yes/No — can this repo's tasks be completed and tested without the DAG?

### Contract: frontend

**New/changed endpoints consumed:**
- `METHOD /api/v2/resource` — [brief description]

**Response shape changes:** [describe or "none"]

**Blocking?** Yes/No

### Contract: other repos

| Repo | Change | Blocking? |
|------|--------|-----------|
| | | |
