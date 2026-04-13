# Domain: Questionnaires

Dynamic forms sent to suppliers as part of data requests. Supports conditional questions, file uploads with manual acceptance, progressive saving, and localization.

## Data Model

```
DataRequest (1) ──→ (N) DataRequestSupplier ──→ (N) RequestedQuestionnaire
                                                          │
                                               ┌──────────┴──────────┐
                                               ▼                     ▼
                                    QuestionnaireSchema      QuestionnaireResponse
                                    (template, JSONB)        (answers, JSONB)
```

### Tables

**`questionnaire_schemas`** — `DocumentBase` (JSONB)
- `document_id`: schema identifier (e.g., `"eudr"`, `"supplier_policies"`)
- `data`: JSONB containing full schema: `questionnaire_id`, `version`, `available`, `title`, `description`, `labels` (localized), `questions` (dict by field name), `sections`, `options`, `country`

**`questionnaire_responses`** — `DocumentBase` (JSONB)
- `document_id`: links to `requested_questionnaire.id`
- `data`: JSONB containing answers keyed by question field name

**`requested_questionnaires`** — `Base`
- Links template to supplier in a data request
- `questionnaire_template_id`: references schema `document_id`
- `completion_status`: `NEW` → `IN_PROGRESS` → `COMPLETED`
- `options`: JSON overrides (e.g., marking file uploads as required)

## Question Types

| Type | Description |
|------|-------------|
| `boolean` | Yes/No toggle |
| `free_text` | Text input (optional regex/length validation) |
| `numeric` | Number input (optional range validation) |
| `drop_down` | Single select from options list |
| `radio` | Radio button selection |
| `date` | Date picker |
| `email` | Email with format validation |
| `url` | URL with format validation |
| `file_upload` | File attachment with manual acceptance workflow |
| `table` | Dynamic table with configurable columns |
| `computed` | Auto-calculated from other answers |
| `questionsGroup` | Container for grouping related questions |
| `empty` | Spacer/separator |

## Conditional Logic (Triggers)

Questions can be conditionally shown/hidden based on answers to other questions:

```json
{
  "fieldName": "organic_certificate",
  "children": [
    {
      "trigger": { "type": "eq", "value": true },
      "fieldName": "is_organic"
    }
  ]
}
```

Trigger types: `always`, `eq`, `neq`, `gt`, `lt`, `in`, `any`, `all`, `file_uploaded`, `item_selected`

## File Upload + Manual Acceptance

1. Supplier uploads file → stored in GCS via signed URL
2. Answer stores `correlation_id` and `original_filename`
3. Admin reviews → calls `PATCH /questionnaires/{id}/answer` to set `manual_acceptance_status`
4. Status: `pending` → `accepted` or `denied`
5. Orphaned files cleaned up via `cleanup_orphaned_files()`

## Key Flows

### Supplier answering a questionnaire
1. Supplier opens questionnaire → `GET /questionnaires/{schema_id}` returns schema
2. Options from `RequestedQuestionnaire.options` customize the schema
3. Save progress → `PUT /questionnaires/{id}/save` with `status: IN_PROGRESS`
4. Validation runs (partial for IN_PROGRESS, full for COMPLETED)
5. Final submit → `PUT /questionnaires/{id}/save` with `status: COMPLETED`
6. Response stored in `questionnaire_responses` table

## Key Files

| File | Purpose |
|------|---------|
| `src/models/questionnaire_model.py` | All Pydantic models (Question, Answer, Trigger, Validation) |
| `src/services/questionnaire_service.py` | Business logic |
| `src/services/questionnaire_validation_service.py` | Answer validation with partial submission support |
| `src/api/v2/controllers/questionnaire_controller.py` | REST endpoints |
| `src/sqlalchemy_pg/models/questionnaire_schema_model.py` | Schema ORM model (DocumentBase) |
| `src/sqlalchemy_pg/models/questionnaire_response_model.py` | Response ORM model (DocumentBase) |
| `src/sqlalchemy_pg/models/requested_questionnaires_model.py` | Tracking model (Base) |

## Gotchas

- Schemas use `DocumentBase` (JSONB), not `Base` — no UUID `id`, uses `document_id` instead
- Question field names use `__N` suffixes for entity instances (e.g., `supplier_name__1`, `supplier_name__2`)
- Options can override schema behavior at the per-request level
- Validation differs between `IN_PROGRESS` (lenient) and `COMPLETED` (strict)
- Localization uses `LocalizedString` with `en`, `es`, `it` fields
