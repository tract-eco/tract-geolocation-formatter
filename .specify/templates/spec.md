# Spec: [Title]

| Field  | Value      |
|--------|------------|
| Ticket | DEV-XXX    |
| Author |            |
| Date   | YYYY-MM-DD |

---

## Description

<!-- Guidelines:
- One paragraph describing what this spec does and why
-->


## Success Criteria

<!-- Guidelines:
- Each criterion must be measurable and verifiable
-->

- [ ] Criterion 1 (measurable)
- [ ] Criterion 2 (measurable)


## Functional Requirements

<!-- Guidelines:
- Non-trivial requirements only. Omit section if none
-->

## Non-Functional Requirements

<!-- Guidelines:
- Non-trivial requirements only. Omit section if none
-->


## Constraints (DO NOT)

<!-- Guidelines:
- Explicit boundaries: things this spec must NOT do
- Must reference constitution rules where applicable
-->

- Must follow constitution rules (see all files in `.specify/constitutions/**/**`)
- DO NOT [explicit constraint]

---

## Data Model

### Overview

<!-- Guidelines:
- One row per affected table, indicating Create / Alter
-->

| Table        | Action         | Description (optional) |
|--------------|----------------|------------------------|
| `table_name` | Create / Alter |                        |

### Database Definitions

<!-- Guidelines:
- Follows [DBML](https://dbml.dbdiagram.io/docs/)
- All definitions must conform to DBML syntax
- Visualize as ERD using https://dbdiagram.io/d
-->

```dbml
// Existing table — included only to support FK references
Table User {
  id  uuid  [pk]
  // existing columns ...
}

// Alter Post — add archived_at for soft-archiving
Table Post {
  id  uuid  [pk]
  // existing columns ...
  archived_at  timestamp  [null]
}

// Create table
Table Tag {
  id    uuid    [pk]
  name  varchar [not null]
}

// Create table
Table Comment {
  id          uuid     [pk]
  created_at  timestamp
  updated_at  timestamp
  post_id     uuid     [not null, ref: > Post.id]
  author_id   uuid     [not null, ref: > User.id]
  body        text     [not null]
  status      varchar  [not null, default: 'pending', note: 'pending | approved | rejected']
}

// Create table — pivot
Table PostTag {
  id       uuid  [pk]
  post_id  uuid  [not null, ref: > Post.id]
  tag_id   uuid  [not null, ref: > Tag.id]
}
```

### Migration Concerns

<!-- Guidelines:
- Non-trivial concerns only: backfills, indexes, unique constraints, check constraints that enforce state machine business logic at the database level
- Omit section if none
-->

---

## API Specification

### Overview

<!-- Guidelines:
- One row per endpoint, including method, path, and required authorization role
-->

| Method   | Path                     | Description (optional) | Authorization        |
|----------|--------------------------|------------------------|----------------------|
| `GET`    | `/v2/resource-name`      |                        | `DATA_VIEWER_ROLE`   |
| `POST`   | `/v2/resource-name`      |                        | `DATA_UPLOADER_ROLE` |
| `PATCH`  | `/v2/resource-name/{id}` |                        | `DATA_UPLOADER_ROLE` |
| `DELETE` | `/v2/resource-name/{id}` |                        | `DATA_UPLOADER_ROLE` |

### OpenAPI Specification

<!-- Guidelines:
- Follows [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0)
- All schemas and path definitions must conform to OpenAPI 3.1
- Visualize with Swagger using https://editor.swagger.io/
-->

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Resource Management API",
    "version": "1.0.0",
    "description": "An API built using the OpenAPI 3.1 standard."
  },
  "paths": {
    "/v2/resource-name": {
      "get": {
        "summary": "List resources",
        "security": [
          { "bearerAuth": ["DATA_VIEWER_ROLE"] }
        ],
        "parameters": [
          { "name": "filter[x]", "in": "query", "required": false, "schema": { "type": "string" } },
          { "name": "page[limit]", "in": "query", "required": false, "schema": { "type": "integer" } },
          { "name": "page[offset]", "in": "query", "required": false, "schema": { "type": "integer" } }
        ],
        "responses": {
          "200": {
            "description": "Successful response",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/XxxListResponse" }
              }
            }
          }
        }
      },
      "post": {
        "summary": "Create resource",
        "security": [
          { "bearerAuth": ["DATA_UPLOADER_ROLE"] }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": { "$ref": "#/components/schemas/XxxRequest" }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Created",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/XxxResponse" }
              }
            }
          }
        }
      }
    },
    "/v2/resource-name/{id}": {
      "patch": {
        "summary": "Update resource",
        "security": [
          { "bearerAuth": ["DATA_UPLOADER_ROLE"] }
        ],
        "parameters": [
          { "name": "id", "in": "path", "required": true, "schema": { "type": "string", "format": "uuid" } }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": { "$ref": "#/components/schemas/XxxRequest" }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Updated",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/XxxResponse" }
              }
            }
          },
          "404": { "description": "Not found" }
        }
      },
      "delete": {
        "summary": "Delete resource",
        "security": [
          { "bearerAuth": ["DATA_UPLOADER_ROLE"] }
        ],
        "parameters": [
          { "name": "id", "in": "path", "required": true, "schema": { "type": "string", "format": "uuid" } }
        ],
        "responses": {
          "204": { "description": "Deleted" },
          "404": { "description": "Not found" }
        }
      }
    }
  },
  "components": {
    "securitySchemes": {
      "bearerAuth": {
        "type": "http",
        "scheme": "bearer"
      }
    },
    "schemas": {
      "XxxRequest": {
        "type": "object",
        "required": ["data"],
        "properties": {
          "data": {
            "type": "object",
            "required": ["fieldName"],
            "properties": {
              "fieldName": { "type": "string" },
              "relatedResourceId": { "type": "string", "format": "uuid" }
            }
          }
        }
      },
      "XxxResponse": {
        "type": "object",
        "properties": {
          "data": {
            "type": "object",
            "properties": {
              "id": { "type": "string", "format": "uuid" },
              "fieldName": { "type": "string" }
            }
          }
        }
      },
      "XxxListResponse": {
        "type": "object",
        "properties": {
          "data": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/XxxResponse/properties/data"
            }
          },
          "meta": {
            "type": "object",
            "properties": {
              "count": { "type": "integer" }
            }
          }
        }
      }
    }
  }
}
```

## Technical Context

<!-- Guidelines:
- Affected layers: controller / service / repository / model / migration
- Database: PostgreSQL / BigQuery / both
- Domain guides: list only the relevant ones, e.g., `domain-suppliers.md`, `domain-risk.md`
- Existing code to reuse: list specific files/functions if known
-->


## Side Effects

<!-- Guidelines:
- External effects triggered by this feature: Pub/Sub, DAG triggers, GCS operations, BigQuery writes
- Omit section if no side effects
- For each side effect, specify: what triggers it, what it does, which repo/service owns the downstream, and the payload contract
- Reference `.specify/constitutions/domains/ecosystem.md` for cross-repo integration patterns
-->

| Trigger        | Effect          | Target                | Payload / Contract |
|----------------|-----------------|-----------------------|--------------------|
| Record created | Pub/Sub publish | data-cloud-functions  | `{...}`            |
| Batch committed| DAG trigger     | data (Airflow)        | `{...}` via `trigger_dag()` |
| File uploaded  | GCS write       | GCS bucket            | `gs://bucket/path` |


## Acceptance Criteria

<!-- Guidelines:
- One AC per observable behavior (not per endpoint — an endpoint may need several ACs)
- Always cover: happy path, auth failure, key validation error, not-found case
- For multi-step workflows, write one AC per step transition, not one AC for the whole flow
  e.g., "GIVEN a submitted DDS, WHEN 72h passes, THEN amendment is no longer allowed"
- Each AC becomes a pytest case during implementation — if you can't picture the test, the AC is too vague
-->

1. **AC-1:** GIVEN [precondition], WHEN [action], THEN [expected result]
2. **AC-2:** GIVEN [precondition], WHEN [action], THEN [expected result]


## Open Questions

<!-- Guidelines:
- Questions that need clarification before planning
- Remove or move to clarify.md once resolved
-->

- [ ] [Question that needs clarification before planning]


## Changelog

<!-- Guidelines:
- Record spec changes, not implementation changes
- Each row = one meaningful revision
-->

| Date       | Author | Change        |
|------------|--------|---------------|
| YYYY-MM-DD |        | Initial draft |
