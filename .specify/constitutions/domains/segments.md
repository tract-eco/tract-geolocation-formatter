# Domain: Segments & Supply Chain

The core traceability data — product movements through the supply chain.

## Overview

A **segment** represents a unit of supply chain movement from a start node (producer/farm) to an end node (processor/buyer). Segments are the fundamental traceability unit for tracking product flow and EUDR compliance.

## Data Model

```
MasterData (Nodes)
    ├── 1 ← N → TraceabilitySegment (start_node_id, end_node_id)
    │                ├── 1:1 → SegmentTags (JSONB tags)
    │                ├── 1:1 → DDSStatement (via identifiers)
    │                └── N ← N → ExplicitLinkingBatches (linking events)
    │
    └── 1 ← N → GeoSpatial (deforestation data per polygon)
```

### Key Tables

**`TraceabilitySegment`** — Main segment data
- `segment_id` (PK), `transaction_id`, `request_id` (links to DataRequest)
- `start_node_id`, `end_node_id` + denormalized name/type/country for each
- `product`, `sub_product`, `product_certification`, `supply_chain_type`
- `volume` (Float), `unload_date`, `incoterm`
- `previous_transaction_ids` (JSONB array) — upstream segment links
- `identifiers` (JSONB) — DDS refs, batch numbers, container IDs
- `status`, `request_status`, `ttp` (Traceability Trust Percentage)

**`SegmentTags`** — Tag classifications (`segment_id` FK, `tags` JSONB array)
- Tag types: `EUDR`, `SupplyChain`, `Customer`, `InternalReference`, `SustainabilityProgramme`, `General`

**`TraceabilitySegmentsMetadata`** — Computed: `first_segment`, `last_segment`, `next_country`, `customers`

**`SegmentWithMetadataView`** — Read-only view joining segment + metadata for queries

## Key Flows

### Segment query with filters
1. `GET /segments` with filters (product, country, date range, tags, etc.)
2. `SegmentsRepo.build_segments_query_with_filters()` builds SQLAlchemy query
3. Filters unnest JSONB arrays for countries, customers, tags
4. Returns paginated results with metadata

### Explicit linking
1. `POST /segments/link` with segment IDs or filter criteria
2. Creates `ExplicitLinkingEvent` + `ExplicitLinkingBatch` records
3. Triggers `traceability_segment_metadata` Airflow DAG via `composer_service`
4. PubSub notification updates MasterDataManager node status

### DDS extraction
1. `GET /segments/{segmentId}/dds` extracts DDS data
2. Recursive query walks upstream/downstream via `previous_transaction_ids` (max 20 hops)
3. Returns data needed for EU TRACES submission

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/segments` | List with filters, pagination, sort |
| GET | `/segments/filters` | Get interdependent filter options |
| GET | `/segments/{segmentId}/dds` | DDS data for EUDR submission |
| POST | `/segments/link` | Link segments (by ID or filters) |
| DELETE | `/segments/{segment_id}` | Delete segment |

### Supply Chain endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/supply-chain/nodes` | Nodes by geohash + product (GeoJSON) |
| GET | `/supply-chain/aggregated-nodes` | Aggregated by geohash/country |
| GET | `/supply-chain/segments` | Segments by geohash + product |
| GET | `/supply-chain/aggregated-segments` | Aggregated by dimensions |

## Key Files

| File | Purpose |
|------|---------|
| `src/models/segments.py` | Pydantic schemas |
| `src/sqlalchemy_pg/models/segments_models.py` | ORM models (Segment, Tags, Linking, Metadata) |
| `src/services/segments_service.py` | Business logic, linking, DDS extraction |
| `src/services/supply_chain_service.py` | GeoJSON, aggregation, deforestation/legality CTEs |
| `src/api/v2/controllers/segments_controller.py` | Segment endpoints |
| `src/api/v2/controllers/supply_chain_controller.py` | Supply chain endpoints |
| `src/sqlalchemy_pg/repositories/segments_repository.py` | Segment queries, filter builder |
| `src/sqlalchemy_pg/repositories/supply_chain_repository.py` | Raw SQL with CTEs for aggregation |

## Gotchas

- Segments use `segment_id` as PK (not UUID `id` from Base) — this is a legacy pattern
- `SegmentWithMetadataView` is a read-only view — writes go to `TraceabilitySegment`
- `previous_transaction_ids` is JSONB array, not a FK relationship — chain walking uses recursive queries
- Tag filtering requires JSONB unnesting (`jsonb_array_elements`)
- Supply chain repository uses raw SQL with CTEs, not the BaseRepository pattern
