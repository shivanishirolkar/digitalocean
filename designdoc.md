# Secure File Ingestion & Signed URL Service — Design Document

---

## 1. Functional Requirements

### FR-1: Secure File Ingestion
- Accept file uploads via `multipart/form-data`
- Every upload must be associated with a `user_id` (passed via authenticated header or request param)
- Store files in a **non-public directory** on the local filesystem (outside the web root, e.g. `/data/uploads/`)
- Rename files on disk to a UUID to prevent path traversal and filename collisions; preserve the original filename in the database
- Reject uploads that exceed a configurable max file size (default: 10 MB)
- Reject uploads with no file attached or an empty file body

### FR-2: Signed URL Generation
- Authenticated endpoint that accepts a `file_id` and a `ttl_seconds` (time-to-live)
- Only the **file owner** (the user who uploaded) may generate a signed link for that file
- Produce a cryptographically signed URL using **HMAC-SHA256** with a server-side secret key stored in an environment variable (`SIGNING_SECRET`)
- The signed token encodes: `file_id`, `expires_at` (UTC epoch), and the HMAC signature
- The signed URL must remain valid across service restarts (no in-memory nonces or session state)
- Default TTL: 3600 seconds (1 hour); maximum TTL: 86400 seconds (24 hours)

### FR-3: File Retrieval & Validation
- **Public** endpoint (no API key required) that accepts the signed token as a query parameter
- Validates the HMAC signature — rejects tampered tokens with `403 Forbidden`
- Validates the expiration — rejects expired tokens with `410 Gone`
- If valid, streams the file from disk with the correct `Content-Type` and `Content-Disposition` headers
- Returns `404` if the file record exists but the file is missing from disk

### FR-4: Audit & Metadata
- File owners can query metadata for their own files: `filename`, `size_bytes`, `content_type`, `upload_date`
- File owners can list all their uploaded files with pagination
- Every time a signed link is generated, an **audit event** is recorded with: `file_id`, `user_id`, `generated_at`, `expires_at`, `client_ip`
- File owners can retrieve the audit log for any file they own

### FR-5: File Deletion
- File owners can delete their own files
- Deletion removes the database record **and** the file from disk
- Any previously generated signed URLs for a deleted file return `404`

---

## 2. Non-Functional Requirements

### NFR-1: Security
- Files stored outside the web-accessible root — never served directly by the web server
- Signing secret loaded from environment variable, never hardcoded or logged
- HMAC-SHA256 signatures compared using `hmac.compare_digest` (constant-time) to prevent timing attacks
- API key authentication on all mutating endpoints (upload, sign, delete) and metadata reads
- Public download endpoint requires only a valid signed token — no API key
- File paths constructed server-side from UUIDs — user input never used in filesystem paths

### NFR-2: Persistence & Restart Safety
- Signing key is an environment variable → survives container restarts
- Tokens are self-contained (file_id + expiry + signature) → no server-side session state
- Database stores all file metadata and audit records → nothing is lost on restart

### NFR-3: Performance
- Files streamed via `StreamingResponse` — never loaded fully into memory
- Upload size enforced **before** reading the full body where possible
- Pagination on list endpoints to bound response size

### NFR-4: Observability
- Structured JSON logging (`asctime`, `levelname`, `message`)
- Request logging middleware: `method`, `path`, `status_code`, `latency`
- Audit table provides a queryable history of all link generations

### NFR-5: Reliability
- Layered architecture: Routes → Service → Repository
- Service layer raises `ValueError`; routes translate to `HTTPException`
- Global exception handlers for 401, 403, 404, 410, 422, 500
- Database retry on startup (5 attempts, 2-second backoff)

### NFR-6: Testability
- Repository mocked with `AsyncMock` in unit tests
- Integration tests against real Postgres (`file_service_test_db`)
- Celery/background tasks (if any) mocked in all tests
- File system operations use a temporary directory in tests

### NFR-7: Deployment
- Dockerized: `app`, `postgres` services (no Redis/Celery needed initially)
- `scripts/rebuild.sh` and `scripts/deploy.sh` for environment reset and deployment
- Upload directory mounted as a Docker volume so files persist across container rebuilds

---

## 3. API Contract

### Authentication
All endpoints except `GET /download` and `GET /health` require the `X-API-Key` header.

---

### 3.1 File Upload

```
POST /files
Content-Type: multipart/form-data
X-API-Key: <key>
```

**Request (form fields):**

| Field     | Type         | Required | Notes                           |
|-----------|--------------|----------|---------------------------------|
| `file`    | `UploadFile` | yes      | The file binary                 |
| `user_id` | `str`        | yes      | Owner identifier                |

**Response `201 Created`:**
```json
{
  "id": "a1b2c3d4-...",
  "user_id": "user_42",
  "filename": "report.pdf",
  "size_bytes": 204800,
  "content_type": "application/pdf",
  "uploaded_at": "2026-03-02T10:00:00Z"
}
```

**Errors:**

| Status | Condition                  | Body                                    |
|--------|----------------------------|-----------------------------------------|
| 401    | Missing/invalid API key    | `{"error": "unauthorized"}`             |
| 413    | File exceeds max size      | `{"error": "file too large"}`           |
| 422    | Missing file or user_id    | `{"error": "validation error", ...}`    |

---

### 3.2 List User Files

```
GET /files?user_id=user_42&page=1&page_size=10
X-API-Key: <key>
```

**Response `200 OK`:**
```json
{
  "items": [
    {
      "id": "a1b2c3d4-...",
      "user_id": "user_42",
      "filename": "report.pdf",
      "size_bytes": 204800,
      "content_type": "application/pdf",
      "uploaded_at": "2026-03-02T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 10
}
```

---

### 3.3 Get File Metadata

```
GET /files/{file_id}
X-API-Key: <key>
```

**Response `200 OK`:** Same shape as a single item in the list response.

**Errors:**

| Status | Condition       | Body                        |
|--------|-----------------|-----------------------------|
| 404    | File not found  | `{"error": "not found"}`    |

---

### 3.4 Delete File

```
DELETE /files/{file_id}?user_id=user_42
X-API-Key: <key>
```

**Response:** `204 No Content`

**Errors:**

| Status | Condition                            | Body                          |
|--------|--------------------------------------|-------------------------------|
| 403    | `user_id` does not own this file     | `{"error": "forbidden"}`      |
| 404    | File not found                       | `{"error": "not found"}`      |

---

### 3.5 Generate Signed URL

```
POST /files/{file_id}/sign
X-API-Key: <key>
Content-Type: application/json
```

**Request Body:**

| Field         | Type  | Required | Default | Notes                              |
|---------------|-------|----------|---------|------------------------------------|
| `user_id`     | `str` | yes      |         | Must match the file owner          |
| `ttl_seconds` | `int` | no       | 3600    | Min: 60, Max: 86400               |

**Response `201 Created`:**
```json
{
  "download_url": "/download?token=eyJmaWxlX2lkIjoi...",
  "expires_at": "2026-03-02T11:00:00Z"
}
```

**Errors:**

| Status | Condition                        | Body                          |
|--------|----------------------------------|-------------------------------|
| 403    | `user_id` does not own this file | `{"error": "forbidden"}`      |
| 404    | File not found                   | `{"error": "not found"}`      |
| 422    | Invalid TTL range                | `{"error": "validation error"}` |

**Side effect:** An audit event is recorded in the `signed_url_audit` table.

---

### 3.6 Download File (Public)

```
GET /download?token=<signed_token>
```

**No API key required.**

**Response `200 OK`:**
- `Content-Type`: original file MIME type
- `Content-Disposition: attachment; filename="report.pdf"`
- Body: streamed file bytes

**Errors:**

| Status | Condition              | Body                                  |
|--------|------------------------|---------------------------------------|
| 403    | Invalid signature      | `{"error": "invalid signature"}`      |
| 404    | File not found on disk | `{"error": "not found"}`              |
| 410    | Token expired          | `{"error": "link expired"}`           |

---

### 3.7 Get Audit Log

```
GET /files/{file_id}/audit?user_id=user_42&page=1&page_size=20
X-API-Key: <key>
```

**Response `200 OK`:**
```json
{
  "items": [
    {
      "id": "evt-uuid-...",
      "file_id": "a1b2c3d4-...",
      "user_id": "user_42",
      "generated_at": "2026-03-02T10:30:00Z",
      "expires_at": "2026-03-02T11:30:00Z",
      "client_ip": "192.168.1.10"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

**Errors:**

| Status | Condition                        | Body                       |
|--------|----------------------------------|----------------------------|
| 403    | `user_id` does not own this file | `{"error": "forbidden"}`   |
| 404    | File not found                   | `{"error": "not found"}`   |

---

### 3.8 Health Check

```
GET /health
```

**No API key required.**

**Response `200 OK`:**
```json
{"status": "healthy", "database": "connected"}
```

---

## 4. Database Models

### 4.1 `files` Table

| Column         | Type                      | Constraints                        |
|----------------|---------------------------|------------------------------------|
| `id`           | `UUID`                    | Primary key, auto-generated        |
| `user_id`      | `String(255)`             | Not null, indexed                  |
| `filename`     | `String(255)`             | Not null (original upload name)    |
| `stored_path`  | `String(500)`             | Not null (UUID-based path on disk) |
| `size_bytes`   | `BigInteger`              | Not null                           |
| `content_type` | `String(255)`             | Not null                           |
| `uploaded_at`  | `DateTime(timezone=True)` | Not null, auto-set on insert       |
| `updated_at`   | `DateTime(timezone=True)` | Not null, auto-set on insert/update|

**Indexes:**
- `ix_files_user_id` on `user_id` — fast lookup for "list my files"

---

### 4.2 `signed_url_audit` Table

| Column         | Type                      | Constraints                            |
|----------------|---------------------------|----------------------------------------|
| `id`           | `UUID`                    | Primary key, auto-generated            |
| `file_id`      | `UUID`                    | Foreign key → `files.id`, not null     |
| `user_id`      | `String(255)`             | Not null                               |
| `ttl_seconds`  | `Integer`                 | Not null                               |
| `generated_at` | `DateTime(timezone=True)` | Not null, auto-set on insert           |
| `expires_at`   | `DateTime(timezone=True)` | Not null                               |
| `client_ip`    | `String(45)`              | Not null (supports IPv6)               |

**Indexes:**
- `ix_signed_url_audit_file_id` on `file_id` — fast audit log retrieval per file

**Foreign key behavior:**
- `ondelete="CASCADE"` — when a file is deleted, its audit records are also removed

---

## 5. Schemas Summary

### Enums
*(none needed for this service)*

### Request Schemas

| Schema              | Fields                                          |
|---------------------|-------------------------------------------------|
| `SignRequest`       | `user_id: str`, `ttl_seconds: int = 3600`       |

- `@field_validator` on `ttl_seconds`: must be between 60 and 86400

### Response Schemas

| Schema              | Fields                                                                                   |
|---------------------|------------------------------------------------------------------------------------------|
| `FileResponse`      | `id`, `user_id`, `filename`, `size_bytes`, `content_type`, `uploaded_at`                 |
| `FileListResponse`  | `items: list[FileResponse]`, `total`, `page`, `page_size`                                |
| `SignedUrlResponse`  | `download_url: str`, `expires_at: datetime`                                             |
| `AuditEventResponse`| `id`, `file_id`, `user_id`, `generated_at`, `expires_at`, `client_ip`                   |
| `AuditListResponse` | `items: list[AuditEventResponse]`, `total`, `page`, `page_size`                         |
| `ErrorResponse`     | `error: str`, `details: Any = None`                                                     |

All response schemas use `from_attributes = True`.

---

## 6. Signed Token Format

The token is a **Base64url-encoded JSON** payload with an appended HMAC signature:

```
base64url({ "file_id": "<uuid>", "exp": <unix_epoch> }) + "." + base64url(hmac_sha256(payload, SIGNING_SECRET))
```

**Verification steps (in order):**
1. Split token on `"."`  → `payload_b64`, `signature_b64`
2. Recompute HMAC-SHA256 over `payload_b64` using `SIGNING_SECRET`
3. Compare with `signature_b64` using `hmac.compare_digest` → reject if mismatch (`403`)
4. Decode `payload_b64` → extract `exp`
5. Compare `exp` against `datetime.now(UTC)` → reject if expired (`410`)
6. Extract `file_id` → look up file → stream if found (`404` otherwise)

This format is stateless, survives restarts, and requires no database lookup until after signature validation.

---

## 7. Directory Layout

```
app/
├── __init__.py
├── main.py
├── config.py
├── database.py
├── models/
│   ├── __init__.py
│   ├── file_model.py
│   └── audit_model.py
├── schemas/
│   ├── __init__.py
│   ├── file_schema.py
│   └── audit_schema.py
├── repositories/
│   ├── __init__.py
│   ├── file_repository.py
│   └── audit_repository.py
├── services/
│   ├── __init__.py
│   ├── file_service.py
│   └── signing_service.py
├── api/
│   ├── __init__.py
│   └── routes/
│       ├── __init__.py
│       ├── health.py
│       ├── file_routes.py
│       └── download_routes.py
├── core/
│   ├── __init__.py
│   ├── logger.py
│   └── security.py
scripts/
├── rebuild.sh
├── check.sh
└── deploy.sh
tests/
├── __init__.py
├── conftest.py
├── pytest.ini
├── unit/
│   ├── __init__.py
│   └── test_signing_service.py
└── integration/
    ├── __init__.py
    ├── test_health.py
    ├── test_files.py
    ├── test_download.py
    └── test_authentication.py
```

---

## 8. Config Additions

`app/config.py` adds these fields beyond the base settings:

| Field              | Type  | Default              | Notes                              |
|--------------------|-------|----------------------|------------------------------------|
| `SIGNING_SECRET`   | `str` | *(required)*         | HMAC key, loaded from `.env`       |
| `UPLOAD_DIR`       | `str` | `/data/uploads`      | Non-public storage directory       |
| `MAX_FILE_SIZE`    | `int` | `10485760`           | 10 MB in bytes                     |

---
