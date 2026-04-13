# Domain: Data Requests

How data requests work end-to-end. The central workflow for collecting data from suppliers.

## Overview

A data request is a formal request sent to one or more suppliers asking them to provide specific data — files, questionnaires, or both. It tracks the lifecycle from creation through supplier submission to admin acceptance.

## Data Model

```
DataRequest (1) ──→ (N) DataRequestSupplier ──→ (N) RequestedQuestionnaire
     │                        │
     │                        └──→ (N) DataFile (uploaded files)
     │
     └── requester info, type, deadline
```

## Status Lifecycle

```
Requested → Seen → InProgress → Processing → Submitted → Accepted
                                           → Invalid       → Rejected
                                                           → Expired
                                                           → Cancelled
                                                           → Received
```

- **Requested** — Created by admin, notifications sent
- **Seen** — Supplier opened the request
- **InProgress** — Supplier started filling in data
- **Processing** — Files being processed by Airflow DAGs
- **Invalid** — Validation failed during processing
- **Submitted** — Supplier submitted all required data
- **Accepted/Rejected** — Admin reviewed the submission
- **Received** — Data received by the system
- **Expired** — Request passed deadline without submission
- **Cancelled** — Request cancelled by admin

Note: Status lives on `DataRequestSupplier`, not on `DataRequest` itself.

## Creating a Data Request

1. Admin calls `POST /data-requests` with supplier contacts, data types, optional questionnaire template IDs, deadline, description
2. Service creates `DataRequest` + `DataRequestSupplier` for each contact
3. If questionnaires included: creates `RequestedQuestionnaire` per supplier per template
4. PubSub notification sent to trigger email to suppliers

## Management Types

- **bulk** — Multiple suppliers, same data types
- **manual** — Single supplier, custom configuration

## Key Files

| File | Purpose |
|------|---------|
| `src/services/data_request_service.py` | Creation, status management, notifications |
| `src/api/v2/controllers/data_requests_controller.py` | REST endpoints |
| `src/sqlalchemy_pg/models/data_requests_model.py` | ORM models (DataRequest, DataRequestSupplier) |
| `src/services/data_request_supplier_upload_service.py` | File upload handling for suppliers |

## Integration Points

- **Questionnaires** — Linked via `RequestedQuestionnaire` (see `questionnaires.md`)
- **Files** — `DataFile` tracks uploaded files, processed by Airflow DAGs in the `data` repo
- **PubSub** — Email notifications sent via `pubsub_service`
- **Cloud Functions** — `acknowledge_upload` → `copy_files` → `composer_dag_trigger` pipeline

## Gotchas

- `data_request_service.py` is a legacy violation — it raises `HTTPException` directly instead of domain exceptions
- Status transitions are complex — multiple services coordinate (data request service + supplier upload service + questionnaire service)
- The `DataFile` table is shared between this repo and the `data` repo — schema changes require coordination
