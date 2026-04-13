# Domain: DDS (Due Diligence Statements)

The compliance-critical flow for EU TRACES submission. Core EUDR feature.

## Overview

A DDS is a legally required due diligence statement that traces a product through the supply chain and submits it to the EU TRACES system.

## Flow

```
1. Create DDS → traces supply chain via TransactionId (max 20 hops)
2. Submit to EU TRACES API (client cert auth)
3. Poll for status updates
4. Amendments/withdrawals possible within 72h window
```

## Status Lifecycle

```
Draft → Submitted → Accepted
                  → Rejected
                  → Amended (within 72h)
                  → Withdrawn (within 72h)
```

## Key Concepts

- **TransactionId tracing** — Follows the supply chain by walking segment connections, up to 20 hops
- **EU TRACES API** — External government API, requires client certificate authentication
- **72h window** — After submission, amendments and withdrawals are only possible within 72 hours
- **DDS splitter** — Splits large statements into compliant chunks

## Key Files

| File | Purpose |
|------|---------|
| `src/services/dds_statement_service.py` | Statement creation, supply chain tracing |
| `src/services/dds_splitter_service.py` | Splits large DDS into compliant chunks |
| `src/api/v2/controllers/dds_statement_controller.py` | REST endpoints |
| `src/services/traces_api/` | EU TRACES API client (cert auth) |

## Cross-Repo Impact

- `data` repo: `dds_submitter` DAG handles actual EU TRACES submission
- `data` repo: `dds_status_monitor` DAG polls for status updates
- DDS reads from segments, master data, and geospatial data in BigQuery
- This repo creates the statement; submission and monitoring happen in the `data` repo
