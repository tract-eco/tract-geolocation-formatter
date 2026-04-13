# Domain: Data Sharing

Share traceability data packages between organizations.

## Overview

Data sharing creates exportable packages containing segments, master data, and geospatial data. Packages are stored in GCS and can be sent to other organizations for import.

## Data Model

```
Package
    ├── manifest (JSON with permissions)
    ├── attachments (ndjson/JSON files in GCS)
    ├── status: CREATED → SHARED → IMPORTED
    └── data types: master_data, segments, geo_spatial
```

## Key Flows

### Create package
1. `POST /sharing/packages` with data type selection + recipient
2. Service queries segments/master data/geospatial data
3. `DataSharingBuilder` aggregates and formats data
4. Manifest + attachment files uploaded to GCS outbox bucket
5. Package record created in PostgreSQL

### Share package
1. `start_sharing()` updates status, shares metadata
2. Cloud Function copies files to recipient org's bucket
3. Recipient's `import_package` Airflow DAG does BigQuery MERGE (upsert)

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/sharing/packages` | Create sharing package |
| GET | `/sharing/packages/{id}` | Get package attachments by data type |

## Key Files

| File | Purpose |
|------|---------|
| `src/services/data_sharing_service.py` | Package creation, manifest, attachments |
| `src/sqlalchemy_pg/models/package_model.py` | Package ORM model |

## Cross-Repo Impact

- Segments repository for querying data to package
- GCS for file storage (outbox bucket)
- Cloud Functions handle cross-org file transfer
- Airflow DAGs handle import on the receiving side
