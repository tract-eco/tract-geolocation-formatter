- Read Base classes reference in `src/sqlalchemy_pg/base/base_model.py`.

| Base           | Use when                            | PK                               | Columns                                                              |
|----------------|-------------------------------------|----------------------------------|----------------------------------------------------------------------|
| `Base`         | New standardized models             | `id: Uuid` (server-generated)    | `id`, `created_at` (server-generated), `updated_at` (server-updated) |
| `DocumentBase` | Models ported from a document store | `document_id: String` (UUID str) | `document_id`, `data: JSONB`, `created_at`, `updated_at`             |
| `LegacyBase`   | Existing non-standardized models    | (custom)                         | (custom)                                                             |

- All new PostgreSQL models MUST inherit from Base.
- All new PostgreSQL models MUST be imported in `src/sqlalchemy_pg/__init__.py`.
- For association/pivot tables that are practically meaningless without their related entity, set `lazy="joined"` on the `relationship()` definition so the join is always issued. For all other relationships, keep the default `lazy="select"` and control eager loading at the query level with `joinedload()`.

- ORM model example (do NOT redeclare `id`, `created_at`, `updated_at` -- they are inherited from `Base`):
```python
# src/sqlalchemy_pg/models/thing_model.py
from sqlalchemy import Column, ForeignKey, String, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy_pg import Base

class Thing(Base):
    __tablename__ = "things"

    # id, created_at, updated_at inherited from Base
    name = Column(String, nullable=False)
    organization_id = Column(Uuid, ForeignKey("organization.id"), nullable=False)
    status = Column(String, nullable=True, default="active")

    organization = relationship("Organization", lazy="select")
```

- If a model needs `TIMESTAMPTZ` instead of the default `DateTime`, explicitly redeclare the timestamp columns in the ORM model:
```python
from sqlalchemy import Column, DateTime
created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
```

- The `updated_at` trigger is handled automatically. The `Rewriter` hook in `alembic/env.py` intercepts `CreateTableOp` and `AddColumnOp` and appends a `CREATE TRIGGER` for any table with an `updated_at` column. Do not write this trigger manually.

- In hand-written migrations, use `sa.text('gen_random_uuid()')` for UUID `server_default`.

- JSONB column pattern in migrations -- use `sa.JSON()` as the type, and cast the default to `jsonb`:
```python
sa.Column("data", sa.JSON(), nullable=True)
sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb"))
sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb"))
```

- For typed arrays, use the PostgreSQL `ARRAY` type:
```python
from sqlalchemy.dialects.postgresql import ARRAY
sa.Column("analysis_types", ARRAY(sa.Text()), nullable=False)
```

- Index patterns in migrations:
```python
# Simple index
op.create_index("ix_things_name", "things", ["name"])

# Unique index
op.create_index("ix_things_reference", "things", ["reference"], unique=True)

# Composite index
op.create_index("ix_things_org_status", "things", ["organization_id", "status"])

# Conditional (partial) index -- must use raw SQL
op.execute("""
    CREATE INDEX ix_things_active ON things (id)
    WHERE status = 'active'
""")

# GIN index for JSONB columns -- must use raw SQL
op.execute("CREATE INDEX ix_things_tags_gin ON things USING gin (tags)")
```

- Foreign key pattern in migrations:
```python
sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organization.id"), nullable=False)
```

- Adding a column to an existing table (always include a matching downgrade):
```python
def upgrade() -> None:
    op.add_column("things", sa.Column("description", sa.String(), nullable=True))
    op.create_index("ix_things_description", "things", ["description"])

def downgrade() -> None:
    op.drop_index("ix_things_description")
    op.drop_column("things", "description")
```

- Seed system: SQL seed files live in `alembic/seeds/` (numbered: `01_country_data.sql`, etc.). They are tracked via SHA256 hash in a `seed_metadata` table and run automatically after migrations by `alembic/seed_runner.py`. Seeds only re-run when the file content changes. Use `-- STATEMENT` delimiter for batching large inserts.

- Common pitfalls:
  - Always write a reversible `downgrade()` in every migration.
  - JSONB server defaults require `::jsonb` cast: `sa.text("'[]'::jsonb")`, not `sa.text("[]")`.
  - Never modify a migration that has already been applied in other environments.
  - Import your new ORM model in `src/sqlalchemy_pg/__init__.py` before running `alembic revision --autogenerate` -- otherwise Alembic will not detect the new table.
  - After autogeneration, review the migration to confirm the `Rewriter` added the `updated_at` trigger.
