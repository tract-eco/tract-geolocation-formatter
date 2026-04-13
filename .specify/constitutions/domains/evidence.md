# Domain: Evidence

Compliance documentation for supply chain nodes. Extracted from questionnaire answers or submitted directly.

## Overview

Evidence records are digital compliance documents (files, metadata) proving that supply chain nodes meet legal and sustainability requirements. They flow from questionnaire submissions through a mapper that extracts structured evidence.

## Data Model

```
Questionnaire (answers)
    ↓ [evidence_mapper_service]
Evidence (DocumentBase, JSONB)
    └── EvidenceDocument (DocumentBase, JSONB)
         └── Files in GCS

Evidence links to:
    ├── Legal categories (compliance framework)
    ├── Supply chain nodes (node-level targeting)
    └── Data request suppliers (who provided it)
```

### Tables

**`evidences`** — `DocumentBase` (JSONB)
- `document_id` (PK, string), `data` (JSONB)
- Data fields: `name`, `level`, `country`, `categories`, `supplierId`, `nodes`

**`evidence_documents`** — `DocumentBase` (JSONB)
- File references, correlation IDs, acceptance status

### Evidence Levels

| Level | Scope |
|-------|-------|
| `COUNTRY` | Evidence for an entire country |
| `NODE` | Evidence for a specific supply chain node |
| `SUPPLIER` | Evidence for a supplier organization |

## Evidence Mapper

Extracts evidence from questionnaire responses automatically:

1. Schema defines "entity questions" (groups that create evidence)
2. Supplier fills in questionnaire, uploads supporting files
3. `EvidenceMapperService.process_entity_groups()` identifies answered entity groups
4. For each group: extracts metadata → `EvidenceDetails` + `EvidenceDocument` list
5. Persisted to JSONB tables

Key methods: `process_entity_groups()`, `extract_evidence_data()`, `extract_document_data()`, `has_uploaded_files()`

## Key Files

| File | Purpose |
|------|---------|
| `src/services/evidence_service.py` | Evidence CRUD |
| `src/services/evidence_mapper_service.py` | Extract evidence from questionnaires |
| `src/sqlalchemy_pg/models/evidence_model.py` | ORM models (DocumentBase) |

## Gotchas

- Evidence uses `DocumentBase` (JSONB), not `Base` — no UUID `id`, uses `document_id` string
- Repositories use `JSONBAdapterMixin` to query JSONB fields
- Evidence is auto-created from questionnaires via the mapper — not typically created via direct API calls
