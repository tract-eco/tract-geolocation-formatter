# Domain: Ecosystem

How the traceability API fits into the larger system. Read during Clarify and Plan phases for any feature with cross-repo impact.

## System Map

```
                        ┌──────────────┐
                        │   frontend   │  TypeScript/React
                        └──────┬───────┘
                               │ REST (JSON:API-style)
                        ┌──────▼───────┐
                   ┌────┤ traceability  ├────┐  Python/FastAPI
                   │    │  (this repo)  │    │
                   │    └──────┬───────┘    │
                   │           │            │
              PostgreSQL    BigQuery     Keycloak
                   │           │
                   │    ┌──────▼───────┐
                   └────┤    data      ├────┐  Python/Airflow
                        │  (DAGs)      │    │
                        └──────┬───────┘    │
                               │            │
                  ┌────────────┼────────┐   │
                  │            │        │   │
           ┌──────▼──┐  ┌─────▼────┐ ┌─▼───▼──┐
           │  cloud   │  │ gee /    │ │  GCS   │
           │functions │  │ gee-     │ │        │
           │          │  │ client   │ │        │
           └──────────┘  └─────────┘  └────────┘
```

## What Each Repo Owns

| Repo | Stack | Owns |
|------|-------|------|
| **traceability** (this repo) | Python, FastAPI, SQLAlchemy | REST API, CRUD, business logic, auth |
| **data** | Python, Airflow 2.10.4 | ETL pipelines, data validation/transformation/loading |
| **frontend** | TypeScript, React 19, TanStack Query v5 | Web UI, user interactions, map display |
| **data-cloud-functions** | Python, Cloud Functions | Event-driven processors (GCS/PubSub triggers) |
| **gee** | Python, Docker batch job | Basic geospatial analysis via Google Earth Engine |
| **tract-gee-client** | Python, Docker batch job | Advanced GEE analytics + map tile URL generation |

## How Traceability Triggers Other Repos

### 1. Trigger a DAG (Airflow)
```python
from services.composer_service import trigger_dag
trigger_dag(dag_id="master_data_manager", data={"event": {...}})
```
Usually dispatched as a background task from a controller.

### 2. Publish to PubSub
```python
pubsub_client.publish(message=json.dumps(payload), topic_id=TOPIC_ID)
```

### 3. Write to shared tables
Traceability writes to PostgreSQL tables that DAGs also read (e.g., `data_files`, `data_requests`).

## Key DAGs

### Data processing
| DAG ID | Purpose | Triggered by |
|--------|---------|-------------|
| `data_request_orchestrator` | Validate, transform, load incoming data | Cloud Function (file upload) |
| `master_data_manager` | Route master data updates/deletes | Traceability API (background task) |
| `export_master_data_to_csv` | Export master data to GCS as CSV | Traceability API |

### Segments
| DAG ID | Purpose | Triggered by |
|--------|---------|-------------|
| `traceability_segment` | Load segment CSV into BigQuery/PostgreSQL | `data_request_orchestrator` |
| `traceability_segment_metadata` | Segment linking and metadata aggregation | Traceability API (background task) |
| `traceability_segments_aggregate_metadata` | DFS graph traversal, TTP propagation | `traceability_segment_metadata` |

### Geolocation & Deforestation
| DAG ID | Purpose | Triggered by |
|--------|---------|-------------|
| `geolocations_ingestion` | Ingest GeoJSON polygon data | `data_request_orchestrator` |
| `submit_geolocations_analysis` | Submit polygons to GEE for analysis | After validation |
| `retrieve_gee_analysis_status` | Poll GEE task status (scheduled, every 3 min) | Scheduled |
| `calculate_defo_status_gee` | Calculate deforestation status from GEE results | After results retrieved |

### DDS
| DAG ID | Purpose | Triggered by |
|--------|---------|-------------|
| `dds_submitter` | Submit DDS to EU TRACES API | Traceability API |
| `dds_status_monitor` | Poll EU TRACES for status updates | Scheduled |

## Cross-Repo Impact Rules

When planning a feature, ask:

1. **Does this change a shared database table?** → Document which DAG SQL templates need updating
2. **Does this need a new DAG or DAG modification?** → Coordinate with data repo
3. **Does this affect the frontend?** → New endpoint = frontend needs new query/component
4. **Does this affect GEE analysis?** → May need `gee` or `tract-gee-client` updates
5. **What does this repo own vs trigger?**
   - **Owns:** settings storage, API endpoints, business logic, audit logging
   - **Triggers:** DAGs (via `composer_service`), notifications (via PubSub)
   - **Does NOT own:** data processing, GEE analysis, file transformation, EU TRACES submission

## Shared Database Tables

### PostgreSQL (both traceability and data write/read)
| Table | Writer | Reader |
|-------|--------|--------|
| `data_files` | cloud-functions, data DAGs | traceability API |
| `data_requests` | traceability API | data DAGs |
| `data_request_suppliers` | traceability API | data DAGs |
| `packages` | traceability API | data DAGs |

### BigQuery (data DAGs write, traceability reads)
| Dataset | Writer | Reader |
|---------|--------|--------|
| `Traceability.*` | data DAGs | traceability API |
| `MasterData.*` | data DAGs | traceability API, gee |
| `GeospatialAnalysis.*` | gee → data DAGs | traceability API |
| `Deforestation.*` | data DAGs | traceability API |

**Rule:** Changing a shared schema requires coordinated changes. Update the spec's cross-repo impact section and ensure the `data` repo SQL templates are updated alongside the traceability ORM models.
