# Secure File Ingestion & Signed URL Service

A FastAPI service for uploading files, generating time-limited signed download URLs using HMAC-SHA256, and maintaining a full audit trail of every link generated.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Local Setup](#local-setup)
4. [Configuration](#configuration)
5. [Running the Service](#running-the-service)
6. [API Reference](#api-reference)
7. [Signed URL Token Format](#signed-url-token-format)
8. [Data Model](#data-model)
9. [Running Tests](#running-tests)
10. [Deploying to DigitalOcean](#deploying-to-digitalocean)
11. [Future Development](#future-development)
12. [Scalability Considerations](#scalability-considerations)

---

## Overview

This service allows users to:

- **Upload files** securely via `multipart/form-data`. Files are stored on disk under UUID names (preventing path traversal), with metadata in PostgreSQL.
- **Generate signed download URLs** with configurable TTL (60 s – 24 h). Tokens are HMAC-SHA256 signed and stateless — they survive service restarts with no session state.
- **Download files** via a public endpoint that only requires a valid, non-expired signed token. No API key needed.
- **List, inspect, and delete** their own files.
- **Audit** every signed URL generated — who requested it, when it expires, and from which IP.

### Non-Functional Highlights

| Concern | Implementation |
|---|---|
| **Security** | Files stored outside web root; HMAC signatures compared in constant time (`hmac.compare_digest`); UUIDs on disk prevent filename attacks |
| **Performance** | Downloads streamed via `StreamingResponse` (64 KB chunks) — never loaded into memory; pagination on list endpoints |
| **Observability** | Structured JSON logging; request latency middleware; queryable audit table |
| **Reliability** | Layered architecture (Routes → Service → Repository); global error handlers; database retry on startup (5 attempts, 2 s backoff) |
| **Testability** | 77 tests, 95% code coverage; unit tests with `AsyncMock`; integration tests against real PostgreSQL |

---

## Architecture

```
app/
├── main.py                  # FastAPI app, lifespan, middleware, error handlers
├── config.py                # Pydantic settings from .env
├── database.py              # Async SQLAlchemy engine + session
├── models/
│   ├── file_model.py        # files table
│   └── audit_model.py       # signed_url_audit table
├── schemas/
│   ├── file_schema.py       # FileResponse, FileListResponse, ErrorResponse
│   └── audit_schema.py      # SignRequest, SignedUrlResponse, AuditListResponse
├── repositories/
│   ├── file_repository.py   # CRUD for files table
│   └── audit_repository.py  # CRUD for audit table
├── services/
│   ├── file_service.py      # Upload, get, list, delete business logic
│   └── signing_service.py   # HMAC token generation & verification
├── api/routes/
│   ├── file_routes.py       # /files endpoints
│   └── download_routes.py   # /download endpoint
├── core/
│   ├── logger.py            # JSON logging setup
│   └── security.py          # (reserved for API key auth)
scripts/
├── deploy.sh                # One-command deploy to DigitalOcean
├── rebuild.sh               # Reset local DB + uploads
├── check.sh                 # Lint/check utilities
└── test_flow.sh             # 7-step end-to-end demo
tests/
├── conftest.py              # Fixtures: test DB, temp uploads, async client
├── unit/                    # Service-level tests with mocked repos
└── integration/             # Full-stack tests against real Postgres
```

---

## Local Setup

### Prerequisites

- **Python 3.12+**
- **PostgreSQL 16+** running locally

### 1. Clone the repository

```bash
git clone git@github.com:shivanishirolkar/digitalocean.git
cd digitalocean
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create the database

```bash
sudo -u postgres createdb filestore_db
```

If needed, set the password for the `postgres` user:

```bash
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

### 5. Create the upload directory

```bash
sudo mkdir -p /data/uploads
sudo chown $USER:$USER /data/uploads
```

### 6. Create a `.env` file

```bash
cp .env.example .env
```

Edit `.env` and set these values:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/filestore_db
LOG_LEVEL=INFO
API_KEY=changeme
SIGNING_SECRET=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
UPLOAD_DIR=/data/uploads
MAX_FILE_SIZE=10485760
```

---

## Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | `str` | *(required)* | Async PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `LOG_LEVEL` | `str` | `INFO` | Python log level |
| `API_KEY` | `str` | `changeme` | API key for authenticated endpoints (Steps 16-17, not yet enforced) |
| `SIGNING_SECRET` | `str` | *(required)* | HMAC-SHA256 key for signing download tokens |
| `UPLOAD_DIR` | `str` | `/data/uploads` | Directory for storing uploaded files |
| `MAX_FILE_SIZE` | `int` | `10485760` | Maximum upload size in bytes (default: 10 MB) |

---

## Running the Service

```bash
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The service creates tables automatically on startup. Verify with:

```bash
curl http://localhost:8000/health
# {"status": "healthy", "database": "connected"}
```

---

## API Reference

### Health Check

```
GET /health
```

No authentication required.

**Response `200`:**
```json
{"status": "healthy", "database": "connected"}
```

---

### Upload a File

```
POST /files
Content-Type: multipart/form-data
```

| Form Field | Type | Required | Description |
|---|---|---|---|
| `file` | binary | yes | The file to upload |
| `user_id` | string | yes | Owner identifier |

**Response `201`:**
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

| Status | Condition | Body |
|---|---|---|
| `413` | File exceeds `MAX_FILE_SIZE` | `{"error": "file too large"}` |
| `422` | Missing file, empty file, or missing `user_id` | `{"error": "validation error", ...}` |

**Example:**
```bash
curl -X POST http://localhost:8000/files \
  -F "file=@report.pdf" \
  -F "user_id=user_42"
```

---

### List Files

```
GET /files?user_id=user_42&page=1&page_size=10
```

Returns a paginated list of all files owned by the given user.

**Response `200`:**
```json
{
  "items": [ { "id": "...", "filename": "report.pdf", ... } ],
  "total": 1,
  "page": 1,
  "page_size": 10
}
```

**Example:**
```bash
curl "http://localhost:8000/files?user_id=user_42"
```

---

### Get File Metadata

```
GET /files/{file_id}
```

**Response `200`:** Single file object (same shape as list items).

**Errors:** `404` if file not found.

**Example:**
```bash
curl http://localhost:8000/files/a1b2c3d4-...
```

---

### Delete a File

```
DELETE /files/{file_id}?user_id=user_42
```

Deletes the file from disk and the database. Any previously generated signed URLs will return `404`.

**Response:** `204 No Content`

**Errors:**

| Status | Condition | Body |
|---|---|---|
| `403` | `user_id` does not own this file | `{"error": "forbidden"}` |
| `404` | File not found | `{"error": "not found"}` |

**Example:**
```bash
curl -X DELETE "http://localhost:8000/files/a1b2c3d4-...?user_id=user_42"
```

---

### Generate a Signed Download URL

```
POST /files/{file_id}/sign
Content-Type: application/json
```

Only the **file owner** can generate a signed link.

**Request body:**

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `user_id` | `string` | yes | — | Must match the file owner |
| `ttl_seconds` | `integer` | no | `3600` | Min: 60, Max: 86400 (24 hours) |

**Response `201`:**
```json
{
  "download_url": "/download?token=eyJmaWxlX2lkIjoi...",
  "expires_at": "2026-03-02T11:00:00Z"
}
```

**Errors:**

| Status | Condition | Body |
|---|---|---|
| `403` | `user_id` does not own this file | `{"error": "forbidden"}` |
| `404` | File not found | `{"error": "not found"}` |
| `422` | `ttl_seconds` outside 60–86400 range | `{"error": "validation error", ...}` |

**Side effect:** An audit event is recorded in the `signed_url_audit` table with `file_id`, `user_id`, `generated_at`, `expires_at`, and `client_ip`.

**Example:**
```bash
curl -X POST http://localhost:8000/files/a1b2c3d4-.../sign \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_42", "ttl_seconds": 3600}'
```

---

### Download a File (Public)

```
GET /download?token=<signed_token>
```

**No authentication required.** Anyone with a valid, non-expired token can download the file.

The file is streamed with the correct `Content-Type` and `Content-Disposition: attachment` headers.

**Errors:**

| Status | Condition | Body |
|---|---|---|
| `403` | Token signature is invalid (tampered) | `{"error": "forbidden"}` |
| `404` | File not found in database or on disk | `{"error": "not found"}` |
| `410` | Token has expired | `{"error": "link expired"}` |

**Example:**
```bash
# Use the download_url from the sign response:
curl "http://localhost:8000/download?token=eyJmaWxlX2lkIjoi..." -o report.pdf
```

---

### Get Audit Log

```
GET /files/{file_id}/audit?user_id=user_42&page=1&page_size=20
```

Returns a paginated list of all signed URL generation events for a file. Owner only.

**Response `200`:**
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

| Status | Condition | Body |
|---|---|---|
| `403` | `user_id` does not own this file | `{"error": "forbidden"}` |
| `404` | File not found | `{"error": "not found"}` |

**Example:**
```bash
curl "http://localhost:8000/files/a1b2c3d4-.../audit?user_id=user_42"
```

---

## Signed URL Token Format

Tokens are **stateless** and self-contained — no server-side sessions or database lookups are needed until after signature validation.

```
base64url({"file_id": "<uuid>", "exp": <unix_epoch>}) . base64url(hmac_sha256(payload, SIGNING_SECRET))
```

**Verification steps (in order):**

1. Split the token on `"."` → `payload_b64`, `signature_b64`
2. Recompute HMAC-SHA256 over `payload_b64` using `SIGNING_SECRET`
3. Compare with `signature_b64` using `hmac.compare_digest` (constant-time) → reject if mismatch (`403`)
4. Decode `payload_b64` → extract `exp`
5. Compare `exp` against current UTC time → reject if expired (`410`)
6. Extract `file_id` → look up file in database → stream if found (`404` otherwise)

---

## Data Model

### `files` Table

| Column | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key, auto-generated |
| `user_id` | `String(255)` | File owner, indexed |
| `filename` | `String(255)` | Original upload filename |
| `stored_path` | `String(500)` | UUID-based path on disk |
| `size_bytes` | `BigInteger` | File size in bytes |
| `content_type` | `String(255)` | MIME type |
| `uploaded_at` | `DateTime(tz)` | Auto-set on insert |
| `updated_at` | `DateTime(tz)` | Auto-set on insert/update |

### `signed_url_audit` Table

| Column | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key, auto-generated |
| `file_id` | `UUID` | FK → `files.id` (CASCADE delete) |
| `user_id` | `String(255)` | Who requested the signed URL |
| `ttl_seconds` | `Integer` | Requested TTL |
| `generated_at` | `DateTime(tz)` | When the URL was created |
| `expires_at` | `DateTime(tz)` | When the URL expires |
| `client_ip` | `String(45)` | Requester's IP (supports IPv6) |

---

## Running Tests

```bash
source venv/bin/activate

# Run all 77 tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=term-missing

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v
```

The test suite creates its own database (`filestore_test_db`) and uses a temporary upload directory. No manual setup is needed beyond having PostgreSQL running.

### End-to-End Demo Script

```bash
./scripts/test_flow.sh
```

Runs a 7-step flow against a live server: upload → sign → download → verify SHA-256 → audit → delete → confirm 404.

---

## Deploying to DigitalOcean

### Prerequisites

- A DigitalOcean Droplet running Ubuntu 24.04 with your SSH key added
- The Droplet's public IP address

### One-Command Deploy

Edit `scripts/deploy.sh` and set `DROPLET_IP` to your Droplet's IP, then:

```bash
./scripts/deploy.sh
```

This script:
1. Rsyncs the project to `/app` on the Droplet
2. Installs/updates Python dependencies in the remote venv
3. Restarts the service via systemd (or starts uvicorn manually)
4. Runs a health check to confirm the app is running

### First-Time Droplet Setup

If deploying for the first time, SSH in and install prerequisites:

```bash
ssh root@$DROPLET_IP

apt update && apt install -y python3 python3-venv python3-pip postgresql postgresql-contrib
systemctl enable postgresql && systemctl start postgresql
sudo -u postgres createdb filestore_db
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"

# Create app directory and venv
mkdir -p /app/uploads
cd /app
python3 -m venv venv

# Create .env (adjust values as needed)
cat > .env << EOF
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/filestore_db
LOG_LEVEL=INFO
API_KEY=<your-api-key>
SIGNING_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
UPLOAD_DIR=/app/uploads
MAX_FILE_SIZE=10485760
EOF
```

### systemd Service (Recommended)

The deploy script automatically manages the systemd service if it exists. To set it up:

```bash
cat > /etc/systemd/system/filestore.service << EOF
[Unit]
Description=File Ingestion Service
After=postgresql.service

[Service]
User=root
WorkingDirectory=/app
EnvironmentFile=/app/.env
ExecStart=/app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable filestore
systemctl start filestore
```

---

## Future Development

### Containerization
- **Docker** and **Docker Compose** to containerize the app and PostgreSQL, making deployments reproducible and environment-independent.

### Database Migrations
- **Alembic** for versioned schema migrations, enabling safe schema changes without data loss in production.

### Authentication & Authorization
- **API key middleware** (Steps 16-17) to protect all mutating and metadata endpoints with `X-API-Key` header validation.
- Role-based access control for multi-tenant scenarios.

### Rate Limiting
- Per-user and per-IP rate limiting to prevent abuse of upload and signing endpoints.
- Libraries like `slowapi` or a reverse proxy (nginx) for enforcement.

### Download Tracking
- Track how many times each signed URL was actually used to download a file.
- Store download events with timestamp, client IP, and user agent for analytics.

### Customer-Centric Features
- **File versioning** — upload new versions of a file without losing the original, with the ability to download any version.
- **Folder organization** — allow users to organize files into virtual folders or tag them with metadata.
- **Thumbnail/preview generation** — auto-generate thumbnails for images and preview pages for PDFs.
- **Shareable links with permissions** — allow file owners to create links that restrict access to specific users or email addresses.
- **Notifications** — notify file owners when their signed URLs are used, or when a URL is about to expire.
- **Bulk operations** — upload, download, or delete multiple files in a single request.

---

## Scalability Considerations

### Scaling to 10,000+ Concurrent Users

**Message Queue Architecture (Kafka)**
- Place a **Kafka message queue** between the API and the file processing pipeline. Upload requests are accepted immediately (file bytes saved to a staging area), and a Kafka message triggers background workers to validate, virus-scan, and move the file to permanent storage.
- Workers process and validate at their own rate, decoupling ingestion throughput from validation cost.
- This pattern absorbs traffic spikes without dropping requests.

**Read-Heavy vs. Write-Heavy Workloads**
- **Read-heavy** (many downloads, few uploads): PostgreSQL scales well here with read replicas, connection pooling (PgBouncer), and caching (Redis) for hot file metadata.
- **Write-heavy** (many uploads): Consider a NoSQL store (e.g., DynamoDB, MongoDB) as the metadata backend for higher write throughput and horizontal scaling. PostgreSQL can remain the audit store.

**Horizontal Scaling**
- Run multiple app instances behind a load balancer (nginx, HAProxy, or DigitalOcean Load Balancer).
- Move file storage from local disk to **object storage** (DigitalOcean Spaces / S3) so all instances share the same file backend.
- Use a shared PostgreSQL instance (or managed database) accessible from all app nodes.

### Handling Large Files

**What Determines "Too Big"?**
- The current limit is **10 MB** (`MAX_FILE_SIZE`), configurable via environment variable.
- The limit exists to protect against memory exhaustion, disk fill, and network timeouts on a single-node deployment.

**Handling Insanely Large Files (100 MB – 10 GB+)**
- **Multipart/chunked uploads**: Break large files into chunks (e.g., 5 MB each), upload each chunk independently, then assemble on the server. This prevents timeouts and allows resumable uploads.
- **Presigned upload URLs**: Generate a presigned URL pointing directly to object storage (S3/Spaces). The client uploads directly, bypassing the API server entirely. The server is notified via webhook when the upload completes.
- **Streaming validation**: Validate file type and size incrementally as chunks arrive rather than buffering the entire file.
- **Timeout management**: Set per-request timeouts at the reverse proxy layer (nginx `client_max_body_size`, `proxy_read_timeout`) and at the app layer to prevent hung connections.
- **Background processing**: For virus scanning, format conversion, or thumbnail generation of large files, offload to background workers via the Kafka queue.

---

## Tech Stack

| Component | Technology |
|---|---|
| **Framework** | FastAPI 0.135 |
| **Server** | Uvicorn 0.41 |
| **Database** | PostgreSQL 16 |
| **Async Driver** | asyncpg 0.31 via SQLAlchemy 2.0 |
| **Validation** | Pydantic 2.12 |
| **Testing** | pytest 9.0 + httpx 0.28 |
| **Deployment** | DigitalOcean Droplet, systemd |