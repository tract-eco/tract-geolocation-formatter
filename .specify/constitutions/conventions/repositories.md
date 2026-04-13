- If the repository is new, create `src/sqlalchemy_pg/repositories/xxxx_repository.py`
- Define `XxxxFilters(FilterT)` dataclass. `XxxxFilters` is the concrete filters class name; `FilterT` is the generic type parameter in `base_repository.py`, not a suffix. Implement with `pass` if no filters required.
- `XxxxFilters` defines the intentional filtering contract available to the service layer. Implement filtering by overriding `_apply_filters`.
- Inherit from `src/sqlalchemy_pg/base/base_repository.py` and set `_model`.
```python
from dataclasses import dataclass
from sqlalchemy import Select
from sqlalchemy_pg.base.base_repository import BaseRepository
from sqlalchemy_pg.models.thing_model import Thing

@dataclass
class ThingFilters:
    statuses: list[str] | None = None
    organization_ids: list[str] | None = None

class ThingRepository(BaseRepository[Thing, ThingFilters]):
    _model = Thing

    @classmethod
    def _apply_filters(cls, stmt: Select, filters: ThingFilters) -> Select:
        if filters.statuses:
            stmt = stmt.where(cls._model.status.in_(filters.statuses))
        if filters.organization_ids:
            stmt = stmt.where(cls._model.organization_id.in_(filters.organization_ids))
        return stmt
```
- XxxxFilters fields should always use the plural form (e.g., `statuses: list[str] | None`, not both `status` and `statuses`). Callers filter for a single value by passing a list with one item: `ThingFilters(statuses=["new"])`.
- Every field defined in XxxxFilters MUST be handled in `_apply_filters`. Do not create separate filter methods like `_apply_list_filters`.
- Always favor usage of repository interface inherited from `BaseRepository` instead of creating new methods. The full inherited API (all `@classmethod`):

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `get` | `(session, model_id: str \| UUID)` | `ModelT \| None` | Lookup by PK via `session.get()` |
| `get_one` | `(session, model_id: str \| UUID, filters=None)` | `ModelT \| None` | PK lookup + optional filters |
| `get_many` | `(session, model_ids: list[str] \| list[UUID])` | `Sequence[ModelT]` | Batch PK lookup via `WHERE IN` |
| `get_all` | `(session, filters=None, offset=0, limit=None, sort_by=None, order_by=ASC, with_total=False)` | `tuple[Sequence[ModelT], int \| None]` | Paginated list. Returns `(results, total)` -- total is `None` unless `with_total=True`. Calls `.unique().all()` on results (safe for joined eager loads). |
| `save` | `(session, model: ModelT)` | `ModelT` | `session.add()` + `flush()` |
| `save_many` | `(session, models: list[ModelT])` | `list[ModelT]` | `session.add_all()` + `flush()` |
| `update` | `(session, model_id: str \| UUID, data: dict)` | `None` | Bulk `UPDATE` by PK. Validates that all keys in `data` are valid columns on the model. |
| `update_many` | `(session, model_ids: list, data: dict)` | `None` | Bulk `UPDATE` via `WHERE IN`. Same column validation. |
| `delete` | `(session, model_id: str \| UUID)` | `None` | `session.delete()` + `flush()`. No-op if not found. |

- Override points on BaseRepository:
  - `_apply_filters(stmt, filters)` -- add WHERE clauses for domain-specific filtering. Must return the modified `stmt`.
  - `_apply_sorting(stmt, sort_by, order_by)` -- default maps `sort_by` string to model column via `getattr`. Override for custom sort logic (e.g., JSONB fields, computed sorts). Always fall back to `super()._apply_sorting()` for unhandled fields:
```python
@classmethod
def _apply_sorting(cls, stmt: Select, sort_by: str | None, order_by: OrderBy) -> Select:
    if sort_by == "customField":
        col = cls._model.data["customField"].as_string()
        return stmt.order_by(col.asc() if order_by == OrderBy.ASC else col.desc())
    return super()._apply_sorting(stmt, sort_by, order_by)
```
- For a simple filtered collection query, favor `get_all(session, filters, ...)` with `XxxxFilters` over a custom query method.
- For a simple bulk update by list of PKs, favor `update_many` over a custom `UPDATE` statement.
- For a simple single-record fetch by PK, favor `get` over a custom `SELECT` statement.
- Only if complexity exceeds trivial CRUD requirements, implement a custom method in `xxxx_repository.py` or create a mixin (ONLY IF the implementation is a good candidate for re-usability). Custom methods still reuse `_apply_filters` for the WHERE clause -- do not duplicate filter logic:
```python
@classmethod
def get_with_counts(cls, session: Session, filters: ThingFilters | None = None) -> list[Row]:
    stmt = (
        select(cls._model, func.count(Related.id).label("related_count"))
        .outerjoin(Related, Related.thing_id == cls._model.id)
        .group_by(cls._model.id)
    )
    if filters:
        stmt = cls._apply_filters(stmt, filters)
    return session.execute(stmt).all()
```
- Use `Model.column.key` as keys in data dicts passed to `values()`. Never use plain string literals as dict keys for column names.
- Always use `.where()` instead of the legacy `.filter()` method in custom SQLAlchemy queries.
- Repository methods never call `session.commit()`. Always call `session.flush()` after writes so that database-server-generated values (UUID, timestamps) are available without ending the transaction. Commit is handled at the request boundary.
- The default `lazy="select"` on relationships causes N+1 when iterating a collection. When writing a repository query that returns models with relationships, always explicitly eager-load needed relationships using `options(joinedload(Model.relationship))`:
```python
@classmethod
def get_all_with_org(cls, session: Session, filters: ThingFilters | None = None) -> Sequence[Thing]:
    stmt = select(cls._model).options(joinedload(cls._model.organization))
    if filters:
        stmt = cls._apply_filters(stmt, filters)
    results = session.scalars(stmt).unique().all()
    return results
```
- When a detail endpoint returns a related entity (e.g., organization, author), define a SQLAlchemy relationship on the model and eager-load it. Do not fetch related entities with separate service calls.
- Trivial data operations must be written with SQLAlchemy Core operations. Raw SQL is only for complex operations that are not possible with the ORM.
- For collection queries that require a different projection (joins across tables, computed columns), create a single custom method. Use `_apply_filters` for the WHERE clause -- do not duplicate filter logic.
- Only single-PK models are supported by BaseRepository -- composite PKs raise `NotImplementedError`.
- Prefer concise Python idioms when readability is preserved. Use set/list/dict comprehensions instead of multi-line loops.
