# Domain: File Management

File upload, download, and storage via Google Cloud Storage. Used by multiple domains (risk documents, data requests, overrides, exports).

## Architecture

All file operations go through signed URLs — the API never receives file content directly.

```
Client
  │
  ├── 1. Request signed URL from API
  │      POST /documents/upload → { signedUrl, documentId }
  │
  ├── 2. Upload file directly to GCS using signed URL
  │      PUT {signedUrl} with file content
  │
  └── 3. Confirm upload / download later
         GET /documents/download/{id} → { signedUrl }
```

## Services

| Service | Purpose |
|---------|---------|
| `GCSService` | Low-level GCS operations: signed URLs, upload from memory, download, delete |
| `SignedUrlService` | Bucket resolution, filename validation, permission checks |
| `FileUploadManager` | Context manager for upload lifecycle (create URLs → confirm) |
| `FileService` | Basic file metadata CRUD |
| `FileUploadStatusService` | Track upload status, file history |

## GCS Buckets

| Bucket | Purpose |
|--------|---------|
| `DATA_BUCKET` | General data files |
| `DATA_REQUEST_SUPPLIER_UPLOAD_BUCKET` | Supplier file submissions |
| `ERROR_BUCKET` | Processing error reports |
| `EXPORT_MASTER_DATA_BUCKET` | Master data CSV exports |
| `EXPORT_PACKAGE_BUCKET` | Data sharing package files |

## Pattern for Adding File Upload to a New Feature

1. Use `FileUploadManager` as context manager
2. Call `create_document_upload_urls()` to get signed URLs + document IDs
3. Return signed URLs to client
4. Client uploads directly to GCS
5. On confirmation, link document IDs to your domain entity

## Key Files

| File | Purpose |
|------|---------|
| `src/services/gcloud_storage_service.py` | GCS client wrapper |
| `src/services/signed_url_service.py` | URL generation and bucket mapping |
| `src/services/file_service.py` | File metadata operations |
| `src/services/file_upload_status_service.py` | Upload tracking |

## Gotchas

- API never receives file content — always use signed URLs
- Signed URLs expire (typically 15 min for upload, 1 hour for download)
- `SignedUrlService.resolve_bucket_name()` maps logical bucket types to actual bucket names from env vars
- `signed_url_service.py` is a legacy violation — raises `HTTPException` directly
- Orphaned file cleanup is each domain's responsibility (e.g., questionnaire service has `cleanup_orphaned_files()`)
