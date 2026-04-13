# Domain: Analytics

Supply chain metrics and insights from BigQuery.

## Overview

Analytics provides aggregated metrics for dashboards — country volumes, farm counts, supplier metrics, risk data. Reads from BigQuery's denormalized views (Gold layer).

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/analytics/overview-metrics` | Overview metrics (date/product/country filters) |
| GET | `/analytics/sourcing-countries-metrics` | Country-level metrics |

## Key Methods

- `get_overview_metrics_filters()` — Country/farm/supplier/volume aggregations
- `get_country_metrics_filters()` — Country-specific metrics with filters
- `get_country_volume()` — Total volume for a country
- `get_country_risk_filters_list()` — Available filter values

## Key Files

| File | Purpose |
|------|---------|
| `src/services/analytics_service.py` | Metric aggregation logic |

## Integration Points

- Queries BigQuery `Gold.SupplyChainSourcingFarms` view
- Uses PostgreSQL repositories for filter logic
- Consumes risk score data
- Table modified date tracking for cache/staleness
