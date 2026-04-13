# Domain: Deforestation Overrides

Override deforestation classifications when suppliers provide evidence of compliance.

## Overview

When geospatial polygons are classified as `DEFORESTED` by the GEE analysis pipeline, suppliers can submit override evidence (documents + explanation) to challenge the classification. Admins review and approve/reject.

## Flow

```
GEE analysis marks polygon as DEFORESTED
    ↓
Admin requests override evidence (POST /override-evidence-requests)
    ↓ Email notification to supplier
GeoSpatial.monitoring_status = EVIDENCE_REQUESTED
    ↓
Supplier uploads documents via signed URLs
    ↓
Supplier submits override (POST /deforestation-overrides)
    ↓
Admin reviews: ACCEPTED or REJECTED
    ↓ If accepted:
GeoSpatial.deforestation_status = NOT_DEFORESTED
GeoSpatial.monitoring_status = EVIDENCE_PROVIDED
```

## Data Model

```
MasterDataGeoSpatial (polygon with deforestation_status)
    ↓
DeforestationOverrides (explanation, created_by, timestamps)
    ├── DeforestationOverrideGeoAssociations (links to geo_ids)
    └── DeforestationOverrideDocumentAssociations
         └── DeforestationOverrideDocuments (file_name, bucket, uploader)

SubmittedOverrideEvidence (status: NEW → ACCEPTED/REJECTED/CANCELLED)
    ├── SubmittedOverrideEvidenceGeoAssociations
    └── SubmittedOverrideEvidenceDocuments
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/override-evidence-requests` | Request evidence from suppliers for deforested geos |
| POST | `/deforestation-overrides/documents/upload` | Get signed URLs for document upload |
| POST | `/deforestation-overrides` | Create override with explanation + documents |
| GET | `/deforestation-overrides/geo/{geoId}` | Get override for a geo |
| GET | `/deforestation-overrides/documents/download/{documentId}` | Download document |

## Key Files

| File | Purpose |
|------|---------|
| `src/services/deforestation_override_service.py` | Override creation, document management |
| `src/services/override_evidence_request_service.py` | Request flow, email notifications |
| `src/api/v2/controllers/deforestation_override_controller.py` | Endpoints |

## Gotchas

- `override_evidence_request_service.py` is a legacy violation — raises `HTTPException` directly
- GCS for document storage (signed URLs for upload/download)
- Email notifications via PubSub when evidence is requested
- `MasterDataGeoSpatial` table updated with override status — this is a BigQuery table, so writes go through the data repo
