- **Scope:** These conventions apply to `src/api/v0/`, `src/api/v1/` and `src/api/v2/` controllers. For `src/api/v3/` endpoints, follow `.specify/constitutions/domains/v3-migration.md` instead — it overrides response types (`V3ObjectResponse`, `V3PagedResponse`, `V3RequestBody`), error handling (`AppError` + `ErrorMapper`), and dependency injection rules.
- Read `src/api/README.md` for the project's lean JSON:API convention.
- The `{"data": ...}` envelope in the API is handled by the framework. Use `JSONAPIResponse[T]` for responses and `JSONAPIRequest[T]` for requests (both from `common.custom_page`). Pydantic models must define only the inner content — never include a `data` property. Never create `XxxxData` wrapper classes.
- `JSONAPIRequest[T]` wrapping belongs in the controller parameter type annotation (e.g. `payload: JSONAPIRequest[XxxCreateRequest]`), never in the model file. Do not create type aliases like `XxxCreateRequest = JSONAPIRequest[XxxBody]` in model files. Request models use action suffixes: `CreateRequest`, `UpdateRequest`, `PatchRequest` — never `Body` or `Data`.
- Always use `JSONAPIResponse[XxxxResponse]` for return/response type.
- Services SHOULD NOT import request or response models. The controller SHOULD translate between API models and domain models in both directions.
- **1 file per API resource for Pydantic models**: all request and response models for a single API resource live in one file (e.g. `src/models/xxxx_model.py` contains `XxxxCreateRequest`, `XxxxUpdateRequest`, `XxxxResponse`, `XxxxListResponse`, `XxxxDetailResponse`). Do not consolidate models from multiple resources into one file.
- Never create a wrapper model with `data` and `meta` fields manually. Extend `JSONAPIResponse` with a generic `meta` type: `JSONAPIResponse[XxxxResponse, XxxxMeta]`.
- Always name the request body parameter `payload` (e.g. `payload: JSONAPIRequest[XxxCreateRequest]`).
- If `user_identity` is not used in the function body, move the `RolesChecker` dependency to the route decorator: `@router.post("/path", dependencies=[Depends(RolesChecker([ROLE]))])`. Only declare `user_identity: dict = Depends(RolesChecker([ROLE]))` when the identity is needed in the function body.
- If the tech spec's API specification specifies error responses (e.g. 400, 403, 404), every listed status code MUST be handled in the controller. Do not leave any specified error path unimplemented.
- **Controllers must remain thin.** A controller endpoint body should only: (1) extract/validate input, (2) call the service, (3) handle session commit/rollback, (4) return the response. When writing a controller, apply these rules:
  - **Field-level validation** (type, format, required, min/max, regex) belongs in the Pydantic request model, not the controller. If you're writing `if not payload.data.name:` in a controller, add a validator to the model instead.
  - **Business rules** (state checks, cross-field logic, authorization beyond role checks, orchestration) belong in the service. If you're writing `if thing.status == "locked":` in a controller, move it to the service and raise a domain exception.
  - **What stays in the controller:** route declaration, `Depends()` wiring, accessing `payload.data`, calling a single service method, catching domain exceptions → `HTTPException`, session commit/rollback, returning the response wrapper.
- **Session management**: the controller owns the session boundary — commit on success, catch SQLAlchemyError exceptions and roll back. The service coordinates writes but does not commit. The repository always flushes, never commits.
- Do not catch HTTPException to raise it again.
- Do not catch broad Exception, `general_exception_handler` in `src/utils/app_factory.py` already handles this.
- If the tech spec's OpenAPI Specification does not define a success response body, set `status_code=200` in the router decorator and do not return an explicit response from the endpoint function. Do not invent response payloads.
- The controller layer must not import or use SQLAlchemy models or queries directly. All data access must go through service or repository method calls. The only invocations allowed on session objects (`db` / `session`) in a controller are `commit()` and `rollback()`.
- Prefer concise Python idioms when readability is preserved. Use set/list/dict comprehensions instead of multi-line loops.
- Controllers receive services via `Depends(get_xxxx_service)`. Never call service static methods directly.
- All controller endpoints MUST use `async def`. Repositories are synchronous; FastAPI handles the async/sync bridge via `Depends()`.
- **Response wrappers** — use `JSONAPIResponse[T]` for single-item responses, `JSONAPIFilterPage[T]` for paginated list responses. Both are imported from `common.custom_page`. Never return raw dicts or plain Pydantic models from a controller.
  ```python
  # Single item
  from common.custom_page import JSONAPIResponse
  @router.get("/{thing_id}", response_model=JSONAPIResponse[ThingResponse])
  async def get_thing(...) -> JSONAPIResponse[ThingResponse]:
      result = service.get_by_id(session, thing_id)
      return JSONAPIResponse(data=result)

  # Paginated list
  from common.custom_page import JSONAPIFilterPage
  @router.get("", response_model=JSONAPIFilterPage[ThingResponse])
  async def list_things(...) -> JSONAPIFilterPage[ThingResponse]:
      rows, total = service.get_all(session, filters, offset=offset, limit=size)
      return JSONAPIFilterPage(
          data=list(rows),
          offset=page,
          pageSize=size,
          totalRowCount=total,
          pageCount=(total + size - 1) // size if total else 1,
      )
  ```
- **Request body wrapping** — POST/PUT/PATCH endpoints that accept a JSON body with a `data` envelope use `JSONAPIRequest[T]`. Access the inner model via `payload.data`. The parameter MUST be named `payload`.
  ```python
  from common.custom_page import JSONAPIRequest
  @router.post("", status_code=status.HTTP_201_CREATED)
  async def create_thing(
      payload: JSONAPIRequest[ThingCreateRequest],
      ...
  ) -> JSONAPIResponse[ThingResponse]:
      result = service.create(session, payload.data)
      return JSONAPIResponse(data=result)
  ```
- **Status codes table** — use the correct code for each operation:
  - `200 OK` — successful GET, PUT, PATCH
  - `201 Created` — successful POST that creates a resource
  - `204 No Content` — successful DELETE
  - `422 Unprocessable Entity` - trivial validation error (handled by Pydantic if possible)
  - `400 Bad Request` — non-trivial validation error, malformed input
  - `401 Unauthorized` — missing or invalid JWT (handled by auth middleware)
  - `403 Forbidden` — valid JWT but insufficient role (handled by `RolesChecker`)
  - `404 Not Found` — resource does not exist
  - `409 Conflict` — duplicate key, state conflict
  - `500 Internal Server Error` — unhandled exception (handled by `general_exception_handler`)
- **URL conventions** — routes are plural, kebab-case, and verb-free. Version prefix is `/api/v2/`.
  - `GET /things` (list), `GET /things/{id}` (detail), `POST /things` (create), `PUT /things/{id}` (full update), `PATCH /things/{id}` (partial update), `DELETE /things/{id}` (delete), `GET /things/{id}/attachments` (nested resource).
  - No trailing slashes.
- **Query parameter patterns** — use JSON:API-style parameter names:
  - Pagination: `page[limit]`, `page[offset]` — declared as `Query(50, alias="page[limit]")`, `Query(0, alias="page[offset]")`
  - Filtering: `filter[fieldName]=value` — declared as `Query(None, alias="filter[status]")`
  - Sorting: `sort=fieldName` (ascending), `sort=-fieldName` (descending)
  ```python
  @router.get("", dependencies=[Depends(RolesChecker([DATA_VIEWER_ROLE]))])
  async def list_things(
      page_limit: int = Query(50, alias="page[limit]"),
      page_offset: int = Query(0, alias="page[offset]"),
      sort: str = Query("name", alias="sort"),
      status_filter: str | None = Query(None, alias="filter[status]"),
      session: Session = Depends(get_postgres_db),
  ) -> JSONAPIFilterPage[ThingResponse]:
      ...
  ```
- **Session management pattern** — commit on success, rollback on database failure. The service and repository never commit.
  ```python
  from sqlalchemy.exc import SQLAlchemyError

  @router.post("", status_code=status.HTTP_201_CREATED)
  async def create_thing(
      payload: JSONAPIRequest[ThingCreateRequest],
      session: Session = Depends(get_postgres_db),
      service: ThingService = Depends(ThingService),
      user_identity: dict = Depends(RolesChecker([DATA_UPLOADER_ROLE])),
  ) -> JSONAPIResponse[ThingResponse]:
      try:
          result = service.create(session, payload.data)
      except ValidationError as e:
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

      try:
          session.commit()
      except SQLAlchemyError:
          session.rollback()
          raise

      return JSONAPIResponse(data=result)
  ```
- **Error handling** — catch domain exceptions from the service layer and convert them to `HTTPException`. Use `from e` to preserve the exception chain. Domain exceptions live in `common.exceptions`.
  ```python
  from common.exceptions import NotFoundError, ValidationError, NotAcceptableError

  try:
      result = service.do_something(session, thing_id)
  except NotFoundError as e:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
  except ValidationError as e:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
  ```
- **Dependency injection** — inject the database session, services, and auth via FastAPI `Depends()`. Services are injected as instances via their class or a factory function.
  ```python
  from sqlalchemy_pg.base.db_postgres import get_postgres_db

  @router.get("/{thing_id}", response_model=JSONAPIResponse[ThingResponse])
  async def get_thing(
      thing_id: str,
      session: Session = Depends(get_postgres_db),
      service: ThingService = Depends(ThingService),
      user_identity: dict = Depends(RolesChecker([DATA_VIEWER_ROLE])),
  ) -> JSONAPIResponse[ThingResponse]:
      ...
  ```
- **Import ordering in controller files** — four groups, separated by blank lines:
  ```python
  # 1. Standard library
  from uuid import UUID

  # 2. Third-party
  from fastapi import APIRouter, Depends, HTTPException, Query, status
  from sqlalchemy.exc import SQLAlchemyError
  from sqlalchemy.orm import Session

  # 3. Local: common, models, services
  from common.constants import DATA_UPLOADER_ROLE, DATA_VIEWER_ROLE
  from common.custom_page import JSONAPIFilterPage, JSONAPIRequest, JSONAPIResponse
  from common.exceptions import NotFoundError, ValidationError
  from common.keycloak_auth.rbac import RolesChecker
  from models.thing_model import ThingCreateRequest, ThingResponse
  from services.thing_service import ThingService

  # 4. Local: sqlalchemy_pg (DB access only — session provider)
  from sqlalchemy_pg.base.db_postgres import get_postgres_db
  ```
- **Router declaration** — every controller file creates a `router` with `tags` and `prefix`:
  ```python
  router = APIRouter(tags=["Things"], prefix="/things")
  ```
- **Type annotations are mandatory** — every parameter and return type must be annotated. Use `str | None` (not `Optional[str]`), `list[str]` (not `List[str]`).
