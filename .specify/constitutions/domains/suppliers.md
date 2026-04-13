# Domain: Suppliers

Supplier (organization) management with Keycloak user integration.

## Overview

Suppliers are organizations that provide traceability data. Each supplier has contacts (people) who can log in via Keycloak to submit data requests, answer questionnaires, and upload files.

## Data Model

```
Organization (supplier)
    ├── name, products, groups, reference (unique)
    ├── active_status: ACTIVE / INACTIVE
    └── 1 → N: Contact
                 ├── name, email, phone
                 ├── active_status: ACTIVE / INACTIVE
                 └── Keycloak user (DATA_SUPPLIER role)
```

## Key Flows

### Create supplier
1. `POST /suppliers` with org details + contacts
2. Creates `Organization` record
3. For each contact: creates `Contact` record + Keycloak user with `DATA_SUPPLIER` role
4. Validates reference uniqueness

### Delete suppliers
1. `DELETE /suppliers` with list of IDs (bulk)
2. Soft delete: sets `Organization.status = INACTIVE`
3. Deactivates all contacts (`Contact.active_status = INACTIVE`)
4. Background task deactivates Keycloak users

### Edit supplier
1. `PATCH /suppliers/{id}` with updated data
2. Manages contact lifecycle: add new, update existing, deactivate removed
3. Creates Keycloak users for new contacts

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/suppliers` | Create supplier + contacts |
| GET | `/suppliers` | List with filters and sorting |
| GET | `/suppliers/list` | ID/name pairs only |
| GET | `/suppliers/{id}/details` | Supplier with contacts |
| PATCH | `/suppliers/{id}` | Update supplier |
| DELETE | `/suppliers` | Bulk soft delete |

## Key Files

| File | Purpose |
|------|---------|
| `src/services/suppliers_service.py` | CRUD, Keycloak integration |
| `src/api/v2/controllers/suppliers_controller.py` | Endpoints |
| `src/sqlalchemy_pg/models/contact_model.py` | Contact ORM model |

## Integration Points

- Keycloak service for user/role management
- Data requests link suppliers to requested data
- Segments reference suppliers via `DataRequestSupplier`
- Questionnaires are assigned per supplier contact
