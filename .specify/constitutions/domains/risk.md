# Domain: Risk

Country risk assessment, scoring, and risk document management for EUDR compliance.

## Overview

Risk scoring evaluates countries and products against deforestation and compliance criteria. Risk documents provide supporting evidence for risk classifications. EUDR risk classifications track EU regulatory risk levels by country.

## Data Model

```
CountryRiskCategories (risk category definitions)
    ↓
RiskDocuments (uploaded compliance documents)
    └── RiskDocumentCountryCategoryAssociations (links docs to countries + categories)

EUDRRiskClassifications (EU regulatory risk levels per country)
```

## Risk Scores

- Calculated per country per product
- `get_risk_score()` returns scores with configurable filters
- `get_country_average_risk_score()` excludes zero scores from average
- Risk data feeds into analytics dashboards

## Risk Documents

Upload flow:
1. `POST /risk-scores/{country_code}/documents/upload` → get signed URLs
2. Upload files to GCS
3. `POST /risk-scores/{country_code}/documents/upload/update-status` → record in DB
4. Documents linked to country + risk category via association table

Validation: file extension whitelist, document count limits per country/category, risk category existence

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/risk-scores` | Get risk scores for countries/products |
| GET | `/risk-scores/{country_code}` | Country risk metrics |
| GET | `/risk-scores/{country_code}/documents` | Risk documents for country |
| POST | `/risk-scores/{country_code}/documents/upload` | Get upload signed URLs |
| GET | `/risk-scores/documents/download/{document_id}` | Download document |
| GET | `/risk-scores/categories/list` | List all risk categories |

## Key Files

| File | Purpose |
|------|---------|
| `src/services/risk_score_service.py` | Score calculation and retrieval |
| `src/services/risk_category_service.py` | Category definitions |
| `src/services/risk_document_service.py` | Document upload/download management |
| `src/services/risk_document_validation_service.py` | Upload validation rules |
| `src/services/eudr_risk_classifications_service.py` | EU regulatory classifications |

## Gotchas

- `risk_document_repository.py` is a legacy violation — calls `session.commit()` directly
