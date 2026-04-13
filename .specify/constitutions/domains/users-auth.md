# Domain: Users & Authentication

User management and Keycloak integration for identity and access control.

## Overview

Authentication and authorization is handled by Keycloak (OIDC). The API validates JWT tokens and enforces role-based access. User lifecycle (create, activate, deactivate) is managed through the Keycloak admin API.

## Roles

| Role | Purpose |
|------|---------|
| `DATA_ADMIN` | Full access, manage users and suppliers |
| `DATA_UPLOADER` | Upload data, create data requests |
| `DATA_VIEWER` | Read-only access to data |
| `DATA_SUBMITTER` | Submit DDS statements |
| `DATA_SUPPLIER` | Supplier portal access (deprecated — being phased out) |

Roles are defined in `src/common/constants.py`.

## User Status Lifecycle

```
INVITED → ACTIVATED → DEACTIVATED
```

## Auth in Controllers

```python
from common.keycloak_auth.rbac import RolesChecker
from common.constants import DATA_UPLOADER_ROLE

@router.post("/things")
def create_thing(
    user_info: dict = Depends(RolesChecker([DATA_UPLOADER_ROLE])),
):
    user_id = user_info["sub"]
    email = user_info["email"]
    roles = user_info["realm_access"]["roles"]
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/users` | Create user (with Keycloak account) |
| PATCH | `/users/{user_id}` | Activate/deactivate |
| GET | `/users` | List users by role |

## Key Files

| File | Purpose |
|------|---------|
| `src/services/user_service.py` | User lifecycle management |
| `src/services/keycloak_service.py` | Keycloak admin API client |
| `src/common/keycloak_auth/rbac.py` | RolesChecker dependency |
| `src/common/constants.py` | Role constants |

## Integration Points

- Suppliers service creates Keycloak users for contacts
- RolesChecker dependency used on every protected endpoint
- JWT token contains `sub` (user ID), `email`, `realm_access.roles`
