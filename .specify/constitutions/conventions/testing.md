- **Framework:** pytest with `pytest-asyncio` for async routes. Coverage via `pytest-cov`.
- **Structure mirrors source:** `tests/api/`, `tests/controllers/`, `tests/services/`, `tests/models/`, `tests/sqlalchemy_pg/`
- **All tests are unit tests with mocks** -- no test hits a real database. Each layer mocks the layer below it: controller mocks service, service mocks repository, repository mocks session.
- **Run tests:** `PYTHONPATH=src python -m pytest tests/path/to/test_file.py -v` (single file), `PYTHONPATH=src python -m pytest tests/path/to/file.py::TestClass::test_method` (single test), `make test` (all with coverage).
- **Test naming:** `test_{method_name}__{success / failure / specific_edge_case}` (double underscore before the scenario).

- **Controller test pattern -- use `app.dependency_overrides`, NOT `@patch` on the service class.** When a controller uses `Depends(get_xxxx_service)`, override that dependency in the test:
```python
from unittest.mock import MagicMock
import pytest
from fastapi import status
from services.thing_service import ThingService, get_thing_service

class TestThingController:
    @pytest.fixture
    def mock_service(self, test_client):
        mock = MagicMock(spec=ThingService)
        test_client.app.dependency_overrides[get_thing_service] = lambda: mock
        yield mock
        test_client.app.dependency_overrides.pop(get_thing_service, None)

    def test_get_thing__success(self, test_client, mock_service):
        mock_service.get_by_id.return_value = ThingResponse(id=..., name="Test")

        response = test_client.get("/api/v2/things/some-id")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["name"] == "Test"
        mock_service.get_by_id.assert_called_once()

    def test_get_thing__not_found(self, test_client, mock_service):
        mock_service.get_by_id.side_effect = NotFoundError("not found")

        response = test_client.get("/api/v2/things/bad-id")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_thing__unauthorized(self, test_client_invalid_creds, mock_service):
        response = test_client_invalid_creds.get("/api/v2/things/some-id")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        mock_service.get_by_id.assert_not_called()
```

- **Service test pattern -- instantiate the service and inject mock repos via the constructor or attribute, NOT with `@patch`.** Pass a `MagicMock(spec=Session)` as the session argument:
```python
from unittest.mock import MagicMock
from sqlalchemy.orm import Session

class TestThingService:
    @pytest.fixture
    def mock_session(self):
        return MagicMock(spec=Session)

    @pytest.fixture
    def service(self):
        svc = ThingService()
        svc.repository = MagicMock(spec=ThingRepository)
        return svc

    def test_get_by_id__success(self, mock_session, service):
        thing = Thing(id="uuid", name="Test")
        service.repository.get.return_value = thing

        result = service.get_by_id(mock_session, "uuid")

        assert result.name == "Test"
        service.repository.get.assert_called_once_with(mock_session, "uuid")

    def test_get_by_id__not_found(self, mock_session, service):
        service.repository.get.return_value = None

        with pytest.raises(NotFoundError):
            service.get_by_id(mock_session, "bad-id")
```

- **Repository tests are optional.** Only write them for custom `_apply_filters` or query methods. Skip if the repo only uses inherited `BaseRepository` methods.

- **What to test per layer:**
  - Controller: happy path, 403 wrong role, 404 not found, 400/422 validation error. Verify service called with correct args.
  - Service: business rules, exception raising, edge cases (empty lists, null values). Skip if pure passthrough.
  - Repository: only custom `_apply_filters` or query methods.

- **Auth identity fixtures** (from `tests/conftest.py`):

| Fixture | Roles | Use for |
|---------|-------|---------|
| `auth_identity` | Data viewer + Data uploader | Default happy path |
| `invalid_auth` | Invalid roles | 403 Forbidden tests |
| `data_uploader_auth` | Data uploader only | Upload-specific tests |
| `data_viewer_auth` | Data viewer only | Read-only tests |
| `data_admin_auth` | User admin | Admin endpoint tests |
| `data_submitter_auth` | Data submitter | DDS submission tests |

- **Test client fixtures** (from `tests/conftest.py`):

| Fixture | Auth | Use for |
|---------|------|---------|
| `test_client` | Default (viewer + uploader) | Most tests |
| `test_client_invalid_creds` | Invalid roles | Auth failure tests |
| `test_client_data_uploader` | Uploader only | Write endpoint tests |
| `test_client_data_viewer` | Viewer only | Read-only tests |
| `test_client_data_admin` | Admin | Admin tests |
| `test_client_data_submitter` | Submitter | DDS tests |
| `test_public_client` | Public API | Rate-limited public endpoints |

- **Mock session fixture:** use `mock_db` (`MagicMock(spec=Session)`, from `tests/conftest.py`). Legacy aliases `mock_db_session` and `mocked_session` exist but do not use them in new tests.

- **Factory fixture pattern** for dynamic test data -- return a callable that builds instances with defaults:
```python
@pytest.fixture
def make_thing():
    def _make(name: str = "Default", status: str = "active") -> Thing:
        return Thing(id=uuid4(), name=name, status=status)
    return _make

def test_filter_active__success(self, make_thing, service, mock_session):
    active = make_thing(name="Active", status="active")
    inactive = make_thing(name="Inactive", status="inactive")
    service.repository.get_all.return_value = ([active, inactive], 2)

    result = service.get_active(mock_session)

    assert len(result) == 1
    assert result[0].name == "Active"
```

- **Parametrized tests** for testing multiple inputs with the same logic:
```python
@pytest.mark.parametrize("role_fixture,expected_status", [
    ("test_client_data_uploader", 201),
    ("test_client_data_viewer", 403),
    ("test_client_invalid_creds", 403),
])
def test_create_thing__roles(self, role_fixture, expected_status, request, mock_service):
    client = request.getfixturevalue(role_fixture)
    response = client.post("/api/v2/things", json={...})
    assert response.status_code == expected_status
```

- **Async tests:** mark with `@pytest.mark.asyncio` and use `async def`:
```python
@pytest.mark.asyncio
async def test_async_operation__success(self, mock_session, service):
    result = await service.async_method(mock_session, payload)
    assert result.status == "created"
```

- **Acceptance tests map to controller tests:** GIVEN becomes arrange, WHEN becomes act, THEN becomes assert. Each AT from the spec becomes a test method on the controller test class.

- **Import order matters in `tests/conftest.py`:** `google.auth.default()` is patched and `DATABASE_URL` is set before any app imports. Do not rearrange.
