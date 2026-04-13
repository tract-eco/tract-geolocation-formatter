- Every service must be a class with constructor-injected dependencies (repositories + other services). No `@staticmethod`. Example:
  ```python
  class ThingService:
      def __init__(self, thing_repository: ThingRepository, other_service: OtherService):
          self.thing_repository = thing_repository
          self.other_service = other_service
  ```
- Module-level factory function `get_xxxx_service()` wires dependencies via `Depends()` and is what controllers inject. Example:
  ```python
  def get_thing_service(
      thing_repository=Depends(ThingRepository),
      other_service=Depends(get_other_service),
  ) -> ThingService:
      return ThingService(
          thing_repository=thing_repository,
          other_service=other_service,
      )
  ```
- The database session is NOT constructor-injected -- it is passed per-request from the controller to every service method as the first positional argument after `self`. Example: `def get_by_id(self, session: Session, thing_id: UUID) -> ThingResponse:`
- Cross-service dependencies are constructor-injected, never called statically. If ServiceA needs ServiceB, inject ServiceB through the constructor and factory function.
- The service layer must not execute SQLAlchemy operations (ORM or Core) directly. All data access must go through repository methods. The only invocations allowed on session objects (`db` / `session`) in a service are passing them to repository or other service calls.
- Cross-model coordination (updating multiple tables in one operation) belongs in the service layer, not the repository layer. A repository only accesses its own model's table.
- The service layer coordinates writes across multiple models within a single transaction. It calls repository methods and relies on `flush()` being called inside each repository write -- it does not call `commit()` itself.
- Raise domain exceptions (`NotFoundError`, `ValidationError`, `NotAcceptableError`) from `common.exceptions`, never `HTTPException`. The controller catches domain exceptions and maps them to HTTP status codes. Example:
  ```python
  from common.exceptions import NotFoundError, ValidationError

  def get_by_id(self, session: Session, thing_id: UUID) -> ThingResponse:
      thing = self.thing_repository.get(session, thing_id)
      if not thing:
          raise NotFoundError(f"Thing {thing_id} not found")
      return ThingResponse.model_validate(thing, from_attributes=True)
  ```
- Convert ORM models to Pydantic response models with `model_validate(obj, from_attributes=True)`. Never manually map fields when the Pydantic model matches the ORM columns. Example:
  ```python
  return ThingResponse.model_validate(created, from_attributes=True)
  ```
- When the Pydantic model does NOT match the ORM columns one-to-one (renamed fields, nested objects, computed values), construct the Pydantic model explicitly. Example:
  ```python
  return DeforestationOverrideResponse(
      override_id=override.id,
      explanation=override.explanation,
      geo_ids=geo_ids,
  )
  ```
- Use `Model.column.key` as keys in data dicts passed to `update()` or `update_many()`. Never use plain string literals as dict keys for column names.
- Never execute a database operation in a loop, to avoid N+1 queries. Use inherited bulk methods from `BaseRepository` (`save_many`, `update_many`, `get_many`) or custom bulk implementations.
- Prefer concise Python idioms when readability is preserved. Use set/list/dict comprehensions instead of multi-line loops (e.g., `{a.geo_id for e in evidences for a in e.geo_associations}` instead of a nested for-loop with `.add()`).
- Background task functions are module-level plain functions (not methods on the service class). They run after the response is sent, outside the request session. The controller calls `session.commit()` before dispatching. Example:
  ```python
  # In the service module, at module level:
  def update_metadata_task(data: dict | None = None) -> None:
      """Background task -- runs after response is sent."""
      trigger_dag(dag_id=TRACEABILITY_SEGMENT_METADATA_DAG_ID, data=data or {})
      tract_logger.info(f"Background task update_metadata_task executed")

  # In the controller:
  result = service.create(session, payload)
  session.commit()
  background_tasks.add_task(update_metadata_task, {"batch_id": batch_id})
  ```
- PubSub publishing uses `PubSubService` injected via `Depends(get_pubsub_client)` in the controller, then passed to a background task function. Topic IDs are constants from `common.constants`. Example:
  ```python
  def update_master_data_task(data: dict, pubsub_client: PubSubService) -> None:
      message = json.dumps([data.get("start_node_id"), data.get("end_node_id")])
      pubsub_client.publish(message=message, topic_id=NODE_STATUS_UPDATE_TOPIC_ID)

  # In the controller:
  background_tasks.add_task(update_master_data_task, node_data, pubsub_client)
  ```
- DAG triggering uses `trigger_dag` from `services.composer_service`. Usually dispatched as a background task. DAG ID constants live in `common.constants`. Example:
  ```python
  from services.composer_service import trigger_dag
  from common.constants import TRACEABILITY_SEGMENT_METADATA_DAG_ID

  trigger_dag(dag_id=TRACEABILITY_SEGMENT_METADATA_DAG_ID, data={"batch_id": batch_id})
  ```
