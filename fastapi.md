# Step 0 — Git & GitHub Setup

## 1. Configure Git
```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

## 2. Generate SSH Key and Add to GitHub
```bash
ssh-keygen -t ed25519 -C "your@email.com"
# hit enter for all defaults
cat ~/.ssh/id_ed25519.pub
# copy output, go to GitHub → Settings → SSH Keys → New SSH Key → paste
```

## 3. Test the Connection
```bash
ssh -T git@github.com
# should say: Hi username! You've successfully authenticated
```

## 4. Create the Repo
- Go to github.com → New repository
- Name it, set **private**, **do not initialize with README**
- Copy the SSH remote URL

## 5. Initialize and Push
```bash
mkdir project && cd project
git init
echo ".env
__pycache__
*.pyc
.pytest_cache
.coverage" > .gitignore
git add .gitignore
git commit -m "initial commit"
git branch -M main
git remote add origin git@github.com:yourusername/repo-name.git
git push -u origin main
```
---

# 1 — Local Setup

## Prerequisites
- **Python 3.13+** installed locally
- **PostgreSQL 16+** installed and running locally (e.g. via `brew install postgresql@16` on macOS, or `apt install postgresql` on Ubuntu)

## Virtual Environment
Create and activate a Python virtual environment in the project root:
```bash
python3 -m venv venv
source venv/bin/activate
```
All subsequent commands assume the venv is active. Add `venv/` to `.gitignore` — never commit it.

## Database Setup
Create the application database:
```bash
sudo -u postgres createdb filestore_db
# or if using your own user:
createdb filestore_db
```

## Files to Create

### `.env`
Create a `.env` file in the project root with these exact keys:
- `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/filestore_db`
- `LOG_LEVEL=INFO`
- `API_KEY=changeme`
- `SIGNING_SECRET` — a random hex string for HMAC signing (generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`)
- `UPLOAD_DIR=./uploads`
- `MAX_FILE_SIZE=10485760`

Adjust `DATABASE_URL` credentials to match your local Postgres user/password.

> Note: the app won't start yet — `requirements.txt` and `app/main.py` don't exist until prompt 3. Do not attempt to run or verify anything now.

---

# 2 — Project Hygiene

## `.gitignore`
Create a `.gitignore` excluding: `.env`, `__pycache__`, `*.pyc`, `.pytest_cache`, `.coverage`, `venv/`, and `uploads/`.

## `.env.example`
Create a `.env.example` with the same keys as `.env` but placeholder values, so collaborators know what to configure:
- `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/filestore_db`
- `LOG_LEVEL=INFO`
- `API_KEY=your-api-key-here`
- `SIGNING_SECRET=your-signing-secret-here`
- `UPLOAD_DIR=./uploads`
- `MAX_FILE_SIZE=10485760`

---

# 3 — Skeleton

## Folder Structure
Create the following folder structure under `app/`. Add an empty `__init__.py` to every folder. Do not write any application code yet — empty files only.
```
app/
├── __init__.py
├── main.py
├── config.py
├── database.py
├── models/
│   ├── file_model.py
│   └── audit_model.py
├── schemas/
│   ├── file_schema.py
│   └── audit_schema.py
├── repositories/
│   ├── file_repository.py
│   └── audit_repository.py
├── services/
│   ├── file_service.py
│   └── signing_service.py
├── api/
│   └── routes/
│       ├── health.py
│       ├── file_routes.py
│       └── download_routes.py
└── core/
    ├── logger.py
    └── security.py
scripts/
└── (empty for now)
```

## `requirements.txt`
Create a `requirements.txt` with these packages (no pinned versions yet):
```
fastapi
uvicorn
postgres
python-multipart
sqlalchemy
greenlet
asyncpg
pydantic
pydantic-settings
aiofiles
httpx
pytest
pytest-asyncio
pytest-cov
python-json-logger
```

- `python-multipart` — required by FastAPI to parse `multipart/form-data` file uploads (`UploadFile`)
- `aiofiles` — async file I/O for streaming uploads to disk and downloads from disk

## `app/config.py`
Use `pydantic-settings` `BaseSettings` with exactly these fields:
- `DATABASE_URL: str`
- `LOG_LEVEL: str` — defaults to `"INFO"`
- `API_KEY: str` — defaults to `"changeme"`
- `SIGNING_SECRET: str` — HMAC key for signed URLs, no default (required)
- `UPLOAD_DIR: str` — defaults to `"./uploads"`
- `MAX_FILE_SIZE: int` — defaults to `10485760` (10 MB in bytes)

Export a `get_settings()` function decorated with `@lru_cache`.

## `app/main.py`
Create a minimal `app/main.py` containing only:
- An async `lifespan` context manager with placeholder comments for startup and shutdown logic
- A `FastAPI` app instance using that lifespan
- Placeholder comments for routers and middleware
- A `GET /` route returning `{"message": "ok"}`

## Documentation
Add docstrings to every function, class, and module created in this prompt and all subsequent prompts. Docstrings should explain what the function does, its parameters, and its return value.

## Scripts
Create two scripts in `scripts/` and make both executable with `chmod +x`:

**`scripts/rebuild.sh`** — full environment reset. Use when changing `.env`, adding packages to `requirements.txt`, or making database schema changes. Activates the virtual environment, reinstalls all dependencies from `requirements.txt` via `pip install -r requirements.txt`, drops and recreates the `filestore_db` database, starts uvicorn in the background, then runs `scripts/check.sh`.

**`scripts/check.sh`** — lightweight check without rebuilding. Use after code-only changes since uvicorn's `--reload` picks them up automatically. Activates the venv, curls `/health`, and runs `pytest tests/ -v --cov=app`. Exits with a failure message if tests fail.

Both scripts should `source venv/bin/activate` at the top so they work regardless of whether the caller's shell has the venv active.

## Verification
```bash
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000 &
./scripts/check.sh
# Expected: {"message": "ok"} and all tests pass
```

---

# 4 — Logging + Error Handling

## `app/core/logger.py`
Create a `setup_logging()` function that:
- Reads `LOG_LEVEL` from settings
- Configures the root logger to output structured JSON via `python-json-logger`'s `JsonFormatter`
- Includes exactly these fields on every line: `asctime`, `levelname`, `message`
- Outputs to stdout

## `app/main.py` — Logging
Call `setup_logging()` at the very top of `app/main.py`, before anything else.

## `app/main.py` — Request Logging Middleware
Add middleware that logs a single JSON line per request with exactly these fields:
- `method`, `path`, `status_code`, `latency` (seconds, 3 decimal places)

Log at `INFO` level. Example output:
```json
{"asctime": "2026-02-28T10:34:33", "levelname": "INFO", "message": "request", "method": "GET", "path": "/", "status_code": 200, "latency": 0.002}
```

## `app/main.py` — Global Exception Handlers
Register handlers for both `fastapi.HTTPException` and `starlette.exceptions.HTTPException` — FastAPI is built on Starlette and unknown routes raise Starlette's variant before FastAPI can intercept them. Both handlers must be identical and switch on `exc.status_code`:

| Status Code | Response Body |
|---|---|
| 401 | `{"error": "unauthorized"}` |
| 404 | `{"error": "not found"}` |
| 409 | `{"error": "job already exists"}` |
| 429 | `{"error": "too many requests"}` |
| any other | return `exc.detail` as-is |

Also register handlers for:
- `RequestValidationError` → 422 `{"error": "validation error", "details": <cleaned error list>}` — strip the `ctx` key from each error dict before returning, as `ctx` may contain raw Python exception objects that are not JSON serializable
- generic `Exception` → 500 `{"error": "internal server error"}` — log the full traceback at `ERROR` level using `logger.exception` with `method` and `path` before returning

All handlers must serialize the response body using `model_dump(exclude_none=True)` so optional fields set to `None` are never included in the response.

## Verification
```bash
curl http://localhost:8000/
```
Check the terminal where uvicorn is running — a JSON log line matching the format above must appear.

---

# 5 — Basic Endpoints

## `app/api/routes/health.py`
Create two endpoints. No database connection yet.

- `GET /health` → `{"status": "ok"}`
- `GET /metrics` → hardcoded placeholder with a `# TODO: replace with get_file_counts(db)` comment:
  ```json
  {"total_files": 0, "total_size_bytes": 0, "total_signed_urls": 0}
  ```

Register both in `app/main.py`.

## Verification
```bash
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```
Then open http://localhost:8000/docs and confirm all 3 endpoints (`/`, `/health`, `/metrics`) are listed.

---

# 6 — Test Setup

## Folder Structure
```
tests/
├── __init__.py
├── conftest.py
├── pytest.ini
└── integration/
    ├── __init__.py
    └── test_health.py
```

## `tests/pytest.ini`
Set `asyncio_mode = auto`.

## `tests/conftest.py`
Create a function-scoped `AsyncClient` fixture pointing at the FastAPI app from `app.main`. No database setup yet.

## `tests/integration/test_health.py`
Write async tests for these cases:

| Test | Request | Expected Status | Expected Body |
|---|---|---|---|
| `test_root_returns_200` | `GET /` | 200 | `{"message": "ok"}` |
| `test_health_returns_200` | `GET /health` | 200 | `{"status": "ok"}` |
| `test_metrics_returns_200` | `GET /metrics` | 200 | contains keys `total_files`, `total_size_bytes`, `total_signed_urls` all with integer values |
| `test_unknown_route_returns_404` | `GET /unknown` | 404 | `{"error": "not found"}` — this is raised by Starlette before FastAPI intercepts it, so both exception handlers registered in prompt 4 must be in place for this test to pass |

## Verification
```bash
./scripts/check.sh
```

---

# 7 — File Model

## `app/models/file_model.py`
SQLAlchemy model only — no database connection or business logic. Table name: `files`.

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | primary key, auto-generated |
| `user_id` | `String(255)` | not null, indexed |
| `filename` | `String(255)` | not null (original upload name) |
| `stored_path` | `String(500)` | not null (UUID-based path on disk) |
| `size_bytes` | `BigInteger` | not null |
| `content_type` | `String(255)` | not null |
| `uploaded_at` | `DateTime(timezone=True)` | not null, auto-set on insert |
| `updated_at` | `DateTime(timezone=True)` | not null, auto-set on insert and update |

**Index:** `ix_files_user_id` on `user_id` — fast lookup for "list my files".

## `app/models/audit_model.py`
SQLAlchemy model only. Table name: `signed_url_audit`.

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | primary key, auto-generated |
| `file_id` | `UUID` | foreign key → `files.id`, not null, `ondelete="CASCADE"` |
| `user_id` | `String(255)` | not null |
| `ttl_seconds` | `Integer` | not null |
| `generated_at` | `DateTime(timezone=True)` | not null, auto-set on insert |
| `expires_at` | `DateTime(timezone=True)` | not null |
| `client_ip` | `String(45)` | not null (supports IPv6) |

**Index:** `ix_signed_url_audit_file_id` on `file_id` — fast audit log retrieval per file.

**Foreign key behavior:** `ondelete="CASCADE"` — when a file is deleted, its audit records are also removed.

---

# 8 — API Contract

## `app/schemas/file_schema.py`
Schemas only — no database or business logic.

### `FileResponse`
| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `UUID` | yes | |
| `user_id` | `str` | yes | |
| `filename` | `str` | yes | |
| `size_bytes` | `int` | yes | |
| `content_type` | `str` | yes | |
| `uploaded_at` | `datetime` | yes | |

Enable `from_attributes = True` so it can be constructed from a SQLAlchemy model instance.

### `FileListResponse`
| Field | Type | Notes |
|---|---|---|
| `items` | `list[FileResponse]` | |
| `total` | `int` | total files for this user |
| `page` | `int` | 1-indexed |
| `page_size` | `int` | |

## `app/schemas/audit_schema.py`

### `SignRequest`
| Field | Type | Required | Notes |
|---|---|---|---|
| `user_id` | `str` | yes | must match the file owner |
| `ttl_seconds` | `int` | no | defaults to `3600` |

Add a `@field_validator` on `ttl_seconds` that rejects values outside the range 60–86400 with `ValueError("ttl_seconds must be between 60 and 86400")`.

### `SignedUrlResponse`
| Field | Type | Notes |
|---|---|---|
| `download_url` | `str` | |
| `expires_at` | `datetime` | |

### `AuditEventResponse`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | |
| `file_id` | `UUID` | |
| `user_id` | `str` | |
| `generated_at` | `datetime` | |
| `expires_at` | `datetime` | |
| `client_ip` | `str` | |

Enable `from_attributes = True`.

### `AuditListResponse`
| Field | Type | Notes |
|---|---|---|
| `items` | `list[AuditEventResponse]` | |
| `total` | `int` | total audit events for this file |
| `page` | `int` | 1-indexed |
| `page_size` | `int` | |

### `ErrorResponse`
| Field | Type | Notes |
|---|---|---|
| `error` | `str` | |
| `details` | `any` | optional, validation errors only |

Update all exception handlers in `app/main.py` to use `ErrorResponse` as the response body.

---

# 9 — Database Connection

## `app/database.py`
Database connection only — no business logic.
- Async SQLAlchemy engine using `asyncpg` and `DATABASE_URL` from settings
- Async `SessionLocal` via `async_sessionmaker`
- `Base` declarative base for all models
- `get_db` async dependency that yields a session and closes it after the request

## `app/main.py` — Lifespan
Update the startup section to:
- Import all models so SQLAlchemy registers them before `create_all`
- Retry the database connection up to 5 times, with a 2-second sleep between attempts, using `SELECT 1` to verify liveness
- Log and re-raise if all attempts fail
- Call `Base.metadata.create_all` on success

## `app/main.py` — Lifespan (continued)
During startup, also ensure the upload directory from `UPLOAD_DIR` exists. Create it with `os.makedirs(settings.UPLOAD_DIR, exist_ok=True)`.

## `app/api/routes/health.py` — Database Check
Update `GET /health` to test the real database on every request using `get_db`:
- Success: `{"status": "healthy", "database": "connected"}`
- Failure: `{"status": "unhealthy", "database": "unreachable"}` — log the exception before returning

Leave `GET /metrics` returning hardcoded zeros for now — it will be wired to real data in prompt 11 once the repository exists.

## Verification
Run a full rebuild since the database schema is being created:
```bash
./scripts/rebuild.sh
psql -U postgres -d filestore_db -c "\dt"
# Expected: files and signed_url_audit tables visible
```

---

# 10 — Test Database

## `tests/conftest.py`
Replace the existing fixture with one that sets up a real Postgres test database. Rules:
- Use `DATABASE_URL` from settings with the database name replaced by `filestore_test_db`
- Create `filestore_test_db` at session start if it doesn't exist (connect to the default `postgres` database to issue `CREATE DATABASE`)
- Fresh async engine and session per test function
- `Base.metadata.create_all` before each test, `drop_all` after — clean schema every test
- Override the `get_db` dependency on the FastAPI app to use the test session
- Never use `aiosqlite` — always `asyncpg` against real Postgres
- `AsyncClient` fixture uses the app with the overridden dependency
- Create a temporary upload directory per test using `tmp_path` and override `UPLOAD_DIR` in settings to point there

## `tests/integration/test_health.py`
Add:

| Test | Request | Expected Status | Expected Body |
|---|---|---|---|
| `test_health_database_connected` | `GET /health` | 200 | `{"status": "healthy", "database": "connected"}` |

## `tests/integration/test_files.py`
Create the file. Add one test:

| Test | Description |
|---|---|
| `test_files_table_exists` | Query `information_schema.tables` where `table_name = 'files'` and assert exactly one row is returned |
| `test_audit_table_exists` | Query `information_schema.tables` where `table_name = 'signed_url_audit'` and assert exactly one row is returned |

## Verification
```bash
./scripts/rebuild.sh
```

---

# 11 — Repository

## `app/repositories/file_repository.py`
Raw database queries only — no business logic, no validation, no HTTP code. Implement these async functions:

### `create_file(db, user_id: str, filename: str, stored_path: str, size_bytes: int, content_type: str) -> File`
Insert a new row and return the created instance.

### `get_file_by_id(db, file_id: UUID) -> File | None`
Return the matching row or `None`.

### `get_files_by_user(db, user_id: str, page: int, page_size: int) -> tuple[list[File], int]`
Return a page of files for the given user (`LIMIT`/`OFFSET`, 1-indexed) plus a total `COUNT(*)`.

### `delete_file(db, file_id: UUID) -> bool`
Delete the row matching `file_id`. Return `True` on success, `False` if not found.

### `get_file_counts(db) -> dict`
Run aggregate queries on the `files` table. Return a dict with exactly these keys: `total_files` (count of all rows), `total_size_bytes` (sum of `size_bytes`, default `0`), `total_signed_urls` (count of all rows in `signed_url_audit`).

## `app/repositories/audit_repository.py`
Raw database queries only.

### `create_audit_event(db, file_id: UUID, user_id: str, ttl_seconds: int, expires_at: datetime, client_ip: str) -> AuditEvent`
Insert a new audit row and return the created instance.

### `get_audit_events_by_file(db, file_id: UUID, page: int, page_size: int) -> tuple[list[AuditEvent], int]`
Return a page of audit events for the given file (`LIMIT`/`OFFSET`, 1-indexed) plus a total `COUNT(*)`.

## `app/api/routes/health.py` — Wire Metrics
Now that the repository exists, update `GET /metrics` to replace the `# TODO` placeholder — inject `get_db` and call `get_file_counts(db)`. Return the result directly.

## Verification
```bash
./scripts/check.sh
```

---

# 12 — Service

## `app/services/file_service.py`
Business logic only — no direct queries, no HTTP code. All database access through the repository.

### `upload_file(db, user_id: str, file: UploadFile, settings) -> File`
- Validate file size: read the file content and check against `settings.MAX_FILE_SIZE`. If exceeded, raise `ValueError("file too large")`
- Reject empty files: if length is 0, raise `ValueError("empty file")`
- Generate a UUID for the stored filename, preserving the original extension
- Write the file to `settings.UPLOAD_DIR / <uuid>.<ext>` using `aiofiles`
- Call `create_file` from the repository with the metadata and return the result
- If the DB insert fails, delete the file from disk before re-raising

### `get_file(db, file_id: UUID) -> File`
- Call `get_file_by_id`; if `None`, raise `ValueError("file not found")`
- Otherwise return the result

### `list_files(db, user_id: str, page: int, page_size: int) -> tuple[list[File], int]`
Delegate directly to `get_files_by_user` — no additional logic.

### `delete_file(db, file_id: UUID, user_id: str)`
- Call `get_file_by_id`; if `None`, raise `ValueError("file not found")`
- If `file.user_id != user_id`, raise `ValueError("forbidden")`
- Delete the file from disk using `os.remove` (ignore `FileNotFoundError` if already gone)
- Call `delete_file` from the repository

## `app/services/signing_service.py`
Cryptographic signing logic only — no database access, no HTTP code.

### `generate_signed_token(file_id: UUID, ttl_seconds: int, secret: str) -> tuple[str, datetime]`
- Compute `expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)`
- Build payload: `{"file_id": str(file_id), "exp": int(expires_at.timestamp())}`
- JSON-encode and Base64url-encode the payload
- Compute HMAC-SHA256 over the encoded payload using `secret`
- Return `f"{payload_b64}.{signature_b64}"` and `expires_at`

### `verify_signed_token(token: str, secret: str) -> UUID`
- Split on `"."` — if not exactly 2 parts, raise `ValueError("invalid signature")`
- Recompute HMAC-SHA256 over the payload part; compare with `hmac.compare_digest` — if mismatch, raise `ValueError("invalid signature")`
- Decode and parse the payload; extract `exp` — if `datetime.now(UTC) > exp`, raise `ValueError("link expired")`
- Return the `file_id` as a `UUID`

## Verification
```bash
./scripts/check.sh
```

---

# 13 — Unit Test Service Layer

## `tests/unit/test_file_service.py`
Create `tests/unit/` with an `__init__.py` and `test_file_service.py`. Use `unittest.mock.AsyncMock` to mock the repository functions — do not touch the database. Use `tmp_path` for file system operations. Test the service logic in isolation.

### Required Tests
| Test | Description | Expected Behaviour |
|---|---|---|
| `test_upload_file_success` | Valid file under size limit | Service writes file to disk, calls repository `create_file`, returns the result |
| `test_upload_file_too_large` | File exceeds `MAX_FILE_SIZE` | `ValueError("file too large")` raised, repository never called, no file on disk |
| `test_upload_empty_file` | File with 0 bytes | `ValueError("empty file")` raised |
| `test_get_file_success` | `get_file_by_id` returns a file | Service returns it |
| `test_get_file_not_found` | `get_file_by_id` returns `None` | `ValueError("file not found")` raised |
| `test_list_files_delegates` | Call `list_files` | `get_files_by_user` called with correct `user_id`, `page`, and `page_size`, result returned as-is |
| `test_delete_file_success` | `get_file_by_id` returns a file matching `user_id` | Service removes file from disk and calls repository `delete_file` |
| `test_delete_file_not_found` | `get_file_by_id` returns `None` | `ValueError("file not found")` raised, repository `delete_file` never called |
| `test_delete_file_wrong_user` | `get_file_by_id` returns a file with a different `user_id` | `ValueError("forbidden")` raised, repository `delete_file` never called |

## `tests/unit/test_signing_service.py`
Test the signing and verification logic in isolation — no database, no HTTP.

### Required Tests
| Test | Description | Expected Behaviour |
|---|---|---|
| `test_generate_and_verify_roundtrip` | Generate a token, then verify it | Returns the same `file_id` |
| `test_verify_expired_token` | Generate with `ttl_seconds=1`, sleep 2 seconds | `ValueError("link expired")` raised |
| `test_verify_tampered_signature` | Alter the signature portion of a valid token | `ValueError("invalid signature")` raised |
| `test_verify_tampered_payload` | Alter the payload portion of a valid token | `ValueError("invalid signature")` raised |
| `test_verify_wrong_secret` | Generate with one secret, verify with another | `ValueError("invalid signature")` raised |
| `test_verify_malformed_token` | Pass a string with no `.` separator | `ValueError("invalid signature")` raised |

### Edge Cases
After writing the required tests, review `file_service.py` and `signing_service.py` and add any additional edge cases not covered. Leave a comment on each explaining what it covers and why.

## Verification
```bash
./scripts/check.sh
```

---

# 14 — Routes

## `app/api/routes/file_routes.py`
Thin layer only — call the service, return the response. No business logic or direct queries.

### `POST /files`
- Accept `multipart/form-data` with `file: UploadFile` and `user_id: str` (form field)
- Return `FileResponse` with status `201`
- On `ValueError("file too large")` → `HTTPException(413)`
- On `ValueError("empty file")` → `HTTPException(422)`

### `GET /files`
- Query params: `user_id` (required), `page=1`, `page_size=10`
- Return `FileListResponse` with status `200`

### `GET /files/{file_id}`
- Path param `file_id: UUID`
- Return `FileResponse` with status `200`
- On `ValueError("file not found")` → `HTTPException(404)`

### `DELETE /files/{file_id}`
- Path param `file_id: UUID`
- Query param: `user_id` (required)
- Return `204` with no body on success
- On `ValueError("file not found")` → `HTTPException(404)`
- On `ValueError("forbidden")` → `HTTPException(403)`

### `POST /files/{file_id}/sign`
- Path param `file_id: UUID`
- Accept `SignRequest` JSON body
- Verify the file exists and `user_id` matches the file owner — if not, `HTTPException(403)`
- Call `signing_service.generate_signed_token` and `audit_repository.create_audit_event`
- Extract `client_ip` from `request.client.host`
- Return `SignedUrlResponse` with status `201`

### `GET /files/{file_id}/audit`
- Path param `file_id: UUID`
- Query params: `user_id` (required), `page=1`, `page_size=20`
- Verify the file exists and `user_id` matches the file owner — if not, `HTTPException(403)`
- Return `AuditListResponse` with status `200`

## `app/api/routes/download_routes.py`
Public endpoint — no API key required.

### `GET /download`
- Query param: `token` (required)
- Call `signing_service.verify_signed_token`
- On `ValueError("invalid signature")` → `HTTPException(403)`
- On `ValueError("link expired")` → `HTTPException(410)`
- Look up the file in the database — if not found, `HTTPException(404)`
- Verify the file exists on disk — if not, `HTTPException(404)`
- Return `StreamingResponse` with `Content-Type` from `file.content_type` and `Content-Disposition: attachment; filename="<original_filename>"`

Register both routers in `app/main.py`.

## Verification
```bash
./scripts/check.sh
```

---

# 15 — Verify Routes

## Test via Swagger UI
Open http://localhost:8000/docs and upload a file via `POST /files`:
- Set `user_id` to `test_user`
- Attach any small file

Then generate a signed URL via `POST /files/{file_id}/sign`:
```json
{"user_id": "test_user", "ttl_seconds": 3600}
```

Copy the `download_url` from the response and open it in a browser — the file should download.

## Verify in the Database
```bash
psql -U postgres -d filestore_db -c "SELECT id, user_id, filename, size_bytes FROM files;"
psql -U postgres -d filestore_db -c "SELECT * FROM signed_url_audit;"
```

## Verify on Disk
```bash
ls -la ./uploads/
```

---

# 16 — Authentication

## `.env`
Generate a secure API key and replace `API_KEY=changeme`. Run this in your terminal and copy the output:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Paste the result as the value of `API_KEY` in `.env`. Do not print or log it anywhere in the code.

## `app/core/security.py`
Create a single FastAPI dependency `verify_api_key`:
- Read the `X-API-Key` header using `Header(default=None)` — using `Header(...)` would make it required and cause a 422 instead of 401 when the header is missing
- If the header is `None` or does not match `API_KEY` from settings (compared using `secrets.compare_digest`), raise `HTTPException(401)`
- Use `secrets.compare_digest` to prevent timing attacks

## `app/api/routes/file_routes.py`
Apply `verify_api_key` to all file routes via the router's `dependencies` parameter. Do not apply it to `/`, `/health`, `/metrics`, `/download`, `/docs`, or `/openapi.json`.

## Verification
Restart the app since `.env` has changed:
```bash
./scripts/rebuild.sh
```

---

# 17 — Test Authentication

## `tests/conftest.py`
Update the `AsyncClient` fixture to include `X-API-Key: <API_KEY from settings>` by default on every request, so all future tests are written against a secured API from the start.

## `tests/integration/test_authentication.py`
Create the file with these tests:

### Required Tests
| Test | Description | Expected Status | Expected Body |
|---|---|---|---|
| `test_missing_api_key_returns_401` | `POST /files` (multipart upload) with no key | 401 | `{"error": "unauthorized"}` |
| `test_invalid_api_key_returns_401` | `POST /files` with wrong key | 401 | `{"error": "unauthorized"}` |
| `test_valid_api_key_returns_201` | `POST /files` with correct key and valid file | 201 | valid `FileResponse` |
| `test_health_requires_no_api_key` | `GET /health` with no key | 200 | `{"status": "healthy", "database": "connected"}` |
| `test_download_requires_no_api_key` | `GET /download?token=...` with no key | does not return 401 (may return 403/410/404 depending on token validity, but never 401) |

For the 401 tests, override the fixture's default header by passing `headers={"X-API-Key": ""}` and `headers={"X-API-Key": "wrongkey"}` directly in those requests only.

### Edge Cases
Review `app/core/security.py` and add any additional edge cases not covered above. Leave a comment on each explaining what it covers and why.

## Verification
```bash
./scripts/check.sh
```

---

# 18 — Test Routes

## `tests/integration/test_files.py`
Add the following tests using the `AsyncClient` fixture. The fixture already includes the `X-API-Key` header by default — all requests are authenticated. For file uploads, use `httpx`'s `files=` parameter to simulate `multipart/form-data`.

### Happy Path
| Test | Description | Expected Status | Expected Body |
|---|---|---|---|
| `test_upload_file` | `POST /files` with valid file and `user_id` | 201 | `FileResponse` with correct `filename`, `size_bytes`, `content_type` |
| `test_get_file_by_id` | `GET /files/{id}` with existing id | 200 | matching `FileResponse` |
| `test_list_files_empty` | `GET /files?user_id=nobody` with no files | 200 | `{"items": [], "total": 0, "page": 1, "page_size": 10}` |
| `test_list_files_with_uploaded_file` | `GET /files?user_id=test_user` after uploading one | 200 | `total: 1`, file in `items` |

### Validation Errors
| Test | Description | Expected Status |
|---|---|---|
| `test_upload_file_missing_user_id` | No `user_id` form field | 422 |
| `test_upload_file_no_file_attached` | Missing `file` field entirely | 422 |
| `test_list_files_missing_user_id` | `GET /files` with no `user_id` query param | 422 |

### Business Logic Errors
| Test | Description | Expected Status | Expected Body |
|---|---|---|---|
| `test_get_file_fake_uuid` | Valid UUID that doesn't exist | 404 | `{"error": "not found"}` |
| `test_delete_file_not_found` | `DELETE /files/{id}?user_id=x` with fake UUID | 404 | `{"error": "not found"}` |
| `test_delete_file_wrong_user` | `DELETE /files/{id}?user_id=wrong` on another user's file | 403 | `{"error": "forbidden"}` |

### DELETE Happy Path
| Test | Description | Expected Status | Expected Body |
|---|---|---|---|
| `test_delete_file` | `DELETE /files/{id}?user_id=test_user` with valid id | 204 | no body |
| `test_delete_file_twice` | `DELETE /files/{id}` same id twice | 404 on second call | `{"error": "not found"}` |
| `test_delete_file_removes_from_disk` | After delete, verify the stored file no longer exists on disk | 404 | file gone |

### Signing and Download
| Test | Description | Expected Status | Expected Body |
|---|---|---|---|
| `test_sign_file` | `POST /files/{id}/sign` with valid owner | 201 | `SignedUrlResponse` with `download_url` and `expires_at` |
| `test_sign_file_wrong_user` | `POST /files/{id}/sign` with non-owner `user_id` | 403 | `{"error": "forbidden"}` |
| `test_sign_file_not_found` | `POST /files/{fake_id}/sign` | 404 | `{"error": "not found"}` |
| `test_sign_file_invalid_ttl` | `ttl_seconds: 10` (below 60) | 422 | validation error |
| `test_download_valid_token` | Upload → sign → `GET /download?token=...` | 200 | file bytes with correct `Content-Type` |
| `test_download_tampered_token` | Alter the token string | 403 | `{"error": "invalid signature"}` |
| `test_download_expired_token` | Generate token with `ttl_seconds=1`, wait, then download | 410 | `{"error": "link expired"}` |
| `test_download_deleted_file` | Upload → sign → delete file → download | 404 | `{"error": "not found"}` |

### Audit
| Test | Description | Expected Status | Expected Body |
|---|---|---|---|
| `test_audit_log_created_on_sign` | Sign a file, then `GET /files/{id}/audit?user_id=...` | 200 | `total: 1`, audit event with correct `file_id` and `client_ip` |
| `test_audit_log_wrong_user` | `GET /files/{id}/audit?user_id=wrong` | 403 | `{"error": "forbidden"}` |

### Edge Cases
| Test | Description | Expected Status |
|---|---|---|
| `test_list_files_pagination` | `?page=1&page_size=1` after uploading 2 files | 200, `total: 2`, 1 item |
| `test_get_file_invalid_uuid_format` | `GET /files/not-a-uuid` | 422 |
| `test_sign_creates_audit_with_client_ip` | After signing, audit event has a non-empty `client_ip` | 200 |

After writing the above, review `file_routes.py`, `download_routes.py`, and `file_service.py` and add any additional edge case tests you can identify. Leave a comment on each explaining what it covers and why it's worth testing.

## Verification
```bash
./scripts/check.sh
```

---

# 19 — Signing Service Deep Tests

No background workers are needed for this service — file signing is synchronous (just HMAC computation) and file streaming is handled natively by FastAPI's `StreamingResponse`.

## `tests/integration/test_download.py`
Create the file with end-to-end download tests using the `AsyncClient` fixture.

### Required Tests
| Test | Description | Expected Behaviour |
|---|---|---|
| `test_full_upload_sign_download_flow` | Upload a file, sign it, download via the signed URL | Downloaded bytes match the original file content, `Content-Type` matches, `Content-Disposition` contains the original filename |
| `test_download_with_various_content_types` | Upload `.txt`, `.pdf`, `.png` files, sign and download each | Correct `Content-Type` header for each |
| `test_signed_url_works_without_api_key` | Generate a signed URL (with API key), then download without `X-API-Key` header | 200 — proves the download endpoint is public |
| `test_multiple_signed_urls_for_same_file` | Sign the same file 3 times with different TTLs | All 3 tokens work, 3 audit events recorded |
| `test_download_after_file_deleted_from_disk_only` | Upload, sign, manually remove file from disk, then download | 404 |

### Edge Cases
Review `signing_service.py` and `download_routes.py` and add any additional edge cases not covered above. Leave a comment on each explaining what it covers and why.

## `scripts/test_flow.sh`
Create an executable script that demonstrates the full flow:
1. Uploads a test file via `POST /files` with `X-API-Key` header
2. Captures the returned `file_id`
3. Signs the file via `POST /files/{file_id}/sign`
4. Downloads the file via `GET /download?token=...` (no API key)
5. Prints the downloaded content and confirms it matches
6. Queries the audit log via `GET /files/{file_id}/audit`
7. Deletes the file via `DELETE /files/{file_id}`

## Verification
```bash
./scripts/check.sh
```

---

# 20 — Final Cleanup

## Uninstall Unused Packages
Review `requirements.txt` and remove any packages not imported anywhere in the codebase. Update the file after removing them. Run `./scripts/rebuild.sh` after changes.

## Run All Tests
```bash
./scripts/check.sh
```
Review the coverage report. For any file below 80%, add tests to bring it up. The generic 500 handler is difficult to trigger naturally — test it by adding a route in `conftest.py` that deliberately raises an unhandled `Exception`, then assert the response is `{"error": "internal server error"}` with status `500`. Remove the route after testing.

## Verify Locally
Using your `API_KEY` from `.env`:

1. Hit `/health` and confirm `{"status": "healthy", "database": "connected"}`
2. Upload a file and capture the returned `id`
3. Generate a signed URL via `POST /files/{id}/sign`
4. Download the file via the signed URL (no API key)
5. Verify the audit log via `GET /files/{id}/audit`
6. Delete the file and confirm the signed URL now returns `404`

---

# 21 — Deployment to DigitalOcean

## Prerequisites (Manual Steps — Do These Before Running Any Commands)

1. Create a DigitalOcean project and a Droplet with these exact specs:
   - **OS**: Ubuntu 24.04 LTS
   - **RAM**: 1GB, **CPU**: 1 vCPU, **SSD**: 25GB
   - **Region**: San Francisco

2. Copy the public key:
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
   Add it to the Droplet during creation under **Authentication → SSH Keys**.

3. Once created, copy the **public IPv4** from the DigitalOcean dashboard.

## Install Dependencies on the Droplet
SSH into the Droplet and install Python, Postgres, and project dependencies:
```bash
ssh root@$DROPLET_IP

apt update && apt install -y python3.13 python3.13-venv python3-pip postgresql postgresql-contrib

# Start and enable Postgres
systemctl enable postgresql
systemctl start postgresql

# Create the database
sudo -u postgres createdb filestore_db

exit
```

## Copy Project to the Droplet
From your local machine:
```bash
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' --exclude 'venv' --exclude 'uploads' . root@$DROPLET_IP:/app
```

## Set Up the App on the Droplet
```bash
ssh root@$DROPLET_IP
cd /app

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create upload directory
mkdir -p /app/uploads

# Edit .env to match Droplet Postgres credentials and set UPLOAD_DIR=/app/uploads
# Ensure SIGNING_SECRET and API_KEY are set to production values

# Start the app
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
curl http://localhost:8000/health
exit
```

## `scripts/deploy.sh`
Create `scripts/deploy.sh` (executable) that:
- Sets `DROPLET_IP` at the top — replace the placeholder with your actual IP before running
- Reads `API_KEY` from `.env` using `export $(grep -v '^#' .env | xargs)`
- Uses `rsync` to sync the project to the Droplet, excluding `.git`, `__pycache__`, `*.pyc`, `venv`, and `uploads`
- SSHs in to: activate the venv, run `pip install -r requirements.txt`, kill any existing uvicorn process, start uvicorn on `0.0.0.0:8000` in the background
- Waits a few seconds then curls `/health` with the `X-API-Key` header to confirm the app is running

Do not use Docker — the app runs directly inside the venv on the Droplet.

## systemd Service (Optional but Recommended)
For production, create a systemd unit file so the app starts on boot and auto-restarts on crash:

```ini
# /etc/systemd/system/filestore.service
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
```

Enable and start:
```bash
systemctl daemon-reload
systemctl enable filestore
systemctl start filestore
systemctl status filestore
```

## Verification
```bash
./scripts/deploy.sh
curl http://$DROPLET_IP:8000/health
```

---

# 22 — Documentation

## ```README.md```
Create a detailed ```README.md``` covering: project overview, functional and non-functional requirements, full API reference (method, path, request/response, error codes), data model (files + signed_url_audit), signed URL token format, local setup with Python venv + Postgres, deploying to DigitalOcean via ```scripts/deploy.sh```, how to run tests, and future development. Write in clear technical prose.

---

# Notes

## Future Development

- **Alembic** — replace `create_all` with `alembic upgrade head` for migration history, rollback, and safe schema evolution
- **Rate limiting** — `slowapi` with Redis storage backend on `POST /files` to prevent upload abuse
- **Virus scanning** — integrate ClamAV to scan uploaded files before storing
- **S3 backend** — swap local filesystem for S3-compatible object storage (DigitalOcean Spaces) for horizontal scaling
- **File type allowlist** — restrict uploads to specific MIME types
- **User authentication** — replace `user_id` form field with JWT-based auth
- **Graceful shutdown** — flush in-flight requests, close DB connections cleanly
- **Containerization** — add `Dockerfile` and `docker-compose.yml` for portable deployments
- **Nginx reverse proxy** — put Nginx in front of uvicorn on the Droplet for TLS termination, static file serving, and request buffering
- **Multi-environment** — separate `.env.development` and `.env.production` configs, staging Droplet to verify before promoting to production
- **Signed URL revocation** — add ability to invalidate a specific signed URL before expiration

---

## Architecture Cheat Sheet

**Metrics endpoint**
Aggregate counts: `total_files`, `total_size_bytes`, `total_signed_urls`.

---

**Models**
One class per table.
- `files` — `id`, `user_id`, `filename`, `stored_path`, `size_bytes`, `content_type`, `uploaded_at`, `updated_at`
- `signed_url_audit` — `id`, `file_id` (FK), `user_id`, `ttl_seconds`, `generated_at`, `expires_at`, `client_ip`

---

**API Contract**
Enforces what the client must send and what they receive.
- Upload uses `multipart/form-data` with `UploadFile` — not JSON body
- `SignRequest` — `user_id`, `ttl_seconds`
- `FileResponse` — full file metadata
- `FileListResponse` — items, total, page, page_size
- `SignedUrlResponse` — download_url, expires_at
- `AuditListResponse` — items, total, page, page_size
- `ErrorResponse` — error, details (optional)

---

**Repository**
Raw queries only. No decisions.
- `file_repository` — `create_file, get_file_by_id, get_files_by_user, delete_file, get_file_counts`
- `audit_repository` — `create_audit_event, get_audit_events_by_file`

---

**Service**
Business logic and rules. No HTTP code. Raises `ValueError`.
- `file_service` — `upload_file, get_file, list_files, delete_file` (handles disk I/O + ownership checks)
- `signing_service` — `generate_signed_token, verify_signed_token` (pure crypto, no DB)

---

**Routes**
Thin layer only. Calls service, returns schema. Translates `ValueError` → `HTTPException`.
- `file_routes` — `POST /files`, `GET /files`, `GET /files/{id}`, `DELETE /files/{id}`, `POST /files/{id}/sign`, `GET /files/{id}/audit`
- `download_routes` — `GET /download?token=...` (public, no API key)

---

## FastAPI Fundamentals

- **Why `lifespan` instead of `@app.on_event`** — the latter is deprecated
- **Why both `fastapi.HTTPException` and `starlette.exceptions.HTTPException` need handlers** — FastAPI is built on Starlette, and 404s for unknown routes are raised by Starlette before FastAPI sees them
- **Why `Header(default=None)` instead of `Header(...)` in `verify_api_key`** — required headers return 422 instead of 401 when missing
- **Why `secrets.compare_digest` instead of `==`** — constant-time comparison prevents timing attacks
- **Why `python-multipart` is required** — FastAPI's `UploadFile` depends on it for parsing `multipart/form-data`
- **Why `StreamingResponse` for downloads** — streams file bytes without loading the entire file into memory

## Signing & Security

- **Why HMAC-SHA256 instead of JWT** — simpler, no library dependency, sufficient for URL signing
- **Why `hmac.compare_digest` instead of `==`** — constant-time comparison prevents timing-based signature forgery
- **Why Base64url encoding** — URL-safe characters, no padding issues in query parameters
- **Why tokens are stateless** — `file_id` + `exp` + HMAC means no server-side session state, survives restarts
- **Why files are renamed to UUIDs on disk** — prevents path traversal attacks and filename collisions
- **Why upload directory is outside the web root** — files are never directly served by the web server

## SQLAlchemy Async

- **Why `async_sessionmaker` instead of `sessionmaker`** — thread-safe session factory for async contexts
- **Why `get_db` uses `yield` with `try/finally`** — ensures session closes even if the route raises an exception
- **Why `from_attributes = True` on response schemas** — lets Pydantic read from ORM object attributes instead of dict keys
- **Why `ondelete="CASCADE"` on `signed_url_audit.file_id`** — when a file is deleted, its audit trail is automatically cleaned up

## Architecture Decisions

- **Why repository layer exists** — isolates raw queries so the service layer never touches SQL directly; easier to mock in unit tests
- **Why service raises `ValueError` instead of `HTTPException`** — keeps business logic decoupled from HTTP; routes translate errors at the boundary
- **Why unit tests mock the repository with `AsyncMock` instead of hitting the database** — fast, isolated, tests logic not infrastructure
- **Why `create_all` on startup instead of Alembic** — acceptable for a greenfield interview project; you should mention Alembic as the production alternative unprompted
- **Why no Redis or Celery** — this service has no background tasks; signing is synchronous HMAC computation, downloading is native streaming

## Deployment

- **Why `rsync` instead of `scp` in `deploy.sh`** — incremental sync, skips unchanged files, faster on repeat deploys
- **Why systemd instead of bare `nohup`** — auto-starts on boot, auto-restarts on crash, logs via `journalctl`
- **Why venv on the Droplet** — isolates project dependencies from system Python packages; same approach as local dev
- **Why `--host 0.0.0.0`** — binds to all interfaces so the Droplet's public IP can reach the app (default `127.0.0.1` only accepts local connections)

## Testing

- **Why `asyncio_mode = auto` in `pytest.ini`** — avoids having to decorate every async test with `@pytest.mark.asyncio`
- **Why `drop_all` / `create_all` per test instead of per session** — guarantees clean state, prevents test ordering bugs
- **Why `filestore_test_db` instead of reusing `filestore_db`** — never run tests against your dev database
- **Why `tmp_path` for upload directory in tests** — isolated per test, automatically cleaned up, no interference between tests
