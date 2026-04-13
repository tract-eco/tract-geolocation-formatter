# Domain: Master Data

Central repository of supply chain entities (nodes) — farms, factories, warehouses.

## Overview

Master data contains all supply chain nodes with their attributes: name, type, country, GPS coordinates, certifications. Nodes are referenced by segments (as start/end points) and by geospatial analysis.

## Data Model

```
MasterData (nodes)
    ├── node_id (deterministic UUID from attributes)
    ├── NodeName, NodeType, Country
    ├── GPS coordinates, certifications
    ├── requestId (links to DataRequest)
    └── Referenced by: Segments, GeoSpatial, Supply Chain
```

## Key Operations

### Node ID generation
- `generate_node_id()` creates a deterministic UUID from normalized node attributes
- `normalize_string()` removes special chars, lowercases
- `normalize_latitude()` / `normalize_longitude()` validates and rounds coordinates
- Same input always produces the same node_id (deduplication)

### Export
- `POST /master-data/export` triggers Airflow DAG `export_master_data_to_csv`
- Async — DAG writes CSV to GCS, not a synchronous download

### Deletion
- Soft delete with segment existence check (can't delete nodes with active segments)

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/master-data/` | List with filters, geo data, pagination |
| POST | `/master-data/export` | Trigger CSV export via Airflow |
| DELETE | `/master-data/{node_id}` | Soft delete (with segment check) |
| GET | `/master-data/supplier-nodes` | Farm nodes for supplier portal |

## Key Files

| File | Purpose |
|------|---------|
| `src/services/master_data_service.py` | Node management, ID generation, export |
| `src/api/v2/controllers/master_data_controller.py` | Endpoints |
| `src/sqlalchemy_pg/models/models.py` | MasterData ORM model |

## Gotchas

- `master_data_repository.py` is a legacy violation — calls `session.commit()` directly
- Node IDs are deterministic (same attributes = same UUID) — not random UUIDs
- MasterData is primarily written by the `data` repo (Airflow DAGs), this API mostly reads
- Export is async via Airflow, not a synchronous download endpoint
