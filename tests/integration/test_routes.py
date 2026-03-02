"""Integration tests for file routes, download, signing, and audit endpoints.

Tests the full request/response cycle through the FastAPI app using
the AsyncClient fixture. No API key auth is applied yet, so requests
are sent without X-API-Key headers.
"""

import asyncio
import os
import uuid

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_UUID = str(uuid.uuid4())


async def _upload_file(
    client: AsyncClient,
    *,
    user_id: str = "test_user",
    filename: str = "hello.txt",
    content: bytes = b"hello world",
    content_type: str = "text/plain",
) -> dict:
    """Upload a file and return the parsed JSON response."""
    resp = await client.post(
        "/files",
        data={"user_id": user_id},
        files={"file": (filename, content, content_type)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _sign_file(
    client: AsyncClient,
    file_id: str,
    *,
    user_id: str = "test_user",
    ttl_seconds: int = 3600,
) -> dict:
    """Sign a file and return the parsed JSON response."""
    resp = await client.post(
        f"/files/{file_id}/sign",
        json={"user_id": user_id, "ttl_seconds": ttl_seconds},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ===========================================================================
# Happy Path
# ===========================================================================


@pytest.mark.asyncio
async def test_upload_file(client: AsyncClient):
    """POST /files with valid file and user_id returns 201 with FileResponse."""
    data = await _upload_file(client, filename="report.pdf", content=b"pdf-bytes", content_type="application/pdf")
    assert data["filename"] == "report.pdf"
    assert data["size_bytes"] == 9
    assert data["content_type"] == "application/pdf"
    assert data["user_id"] == "test_user"
    assert "id" in data
    assert "uploaded_at" in data


@pytest.mark.asyncio
async def test_get_file_by_id(client: AsyncClient):
    """GET /files/{id} with existing id returns 200 with matching FileResponse."""
    uploaded = await _upload_file(client)
    file_id = uploaded["id"]

    resp = await client.get(f"/files/{file_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == file_id
    assert data["filename"] == "hello.txt"
    assert data["user_id"] == "test_user"


@pytest.mark.asyncio
async def test_list_files_empty(client: AsyncClient):
    """GET /files?user_id=nobody returns 200 with empty list."""
    resp = await client.get("/files", params={"user_id": "nobody"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 10


@pytest.mark.asyncio
async def test_list_files_with_uploaded_file(client: AsyncClient):
    """GET /files?user_id=test_user after uploading one returns total: 1."""
    await _upload_file(client)

    resp = await client.get("/files", params={"user_id": "test_user"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["filename"] == "hello.txt"


# ===========================================================================
# Validation Errors
# ===========================================================================


@pytest.mark.asyncio
async def test_upload_file_missing_user_id(client: AsyncClient):
    """POST /files without user_id form field returns 422."""
    resp = await client.post(
        "/files",
        files={"file": ("test.txt", b"data", "text/plain")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_file_no_file_attached(client: AsyncClient):
    """POST /files with no file field returns 422."""
    resp = await client.post("/files", data={"user_id": "test_user"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_file_too_large(client: AsyncClient):
    """POST /files with file exceeding MAX_FILE_SIZE returns 413.
    Exercises the file-too-large error path through the route layer."""
    from app.config import get_settings

    settings = get_settings()
    oversized = b"x" * (settings.MAX_FILE_SIZE + 1)
    resp = await client.post(
        "/files",
        data={"user_id": "test_user"},
        files={"file": ("big.bin", oversized, "application/octet-stream")},
    )
    assert resp.status_code == 413
    assert resp.json() == {"error": "file too large"}


@pytest.mark.asyncio
async def test_upload_empty_file(client: AsyncClient):
    """POST /files with an empty file body returns 422.
    Exercises the empty-file validation through the route layer."""
    resp = await client.post(
        "/files",
        data={"user_id": "test_user"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_files_missing_user_id(client: AsyncClient):
    """GET /files with no user_id query param returns 422."""
    resp = await client.get("/files")
    assert resp.status_code == 422


# ===========================================================================
# Business Logic Errors
# ===========================================================================


@pytest.mark.asyncio
async def test_get_file_fake_uuid(client: AsyncClient):
    """GET /files/{id} with valid UUID that doesn't exist returns 404."""
    resp = await client.get(f"/files/{FAKE_UUID}")
    assert resp.status_code == 404
    assert resp.json() == {"error": "not found"}


@pytest.mark.asyncio
async def test_delete_file_not_found(client: AsyncClient):
    """DELETE /files/{id}?user_id=x with fake UUID returns 404."""
    resp = await client.delete(f"/files/{FAKE_UUID}", params={"user_id": "x"})
    assert resp.status_code == 404
    assert resp.json() == {"error": "not found"}


@pytest.mark.asyncio
async def test_delete_file_wrong_user(client: AsyncClient):
    """DELETE /files/{id}?user_id=wrong on another user's file returns 403."""
    uploaded = await _upload_file(client, user_id="owner")

    resp = await client.delete(
        f"/files/{uploaded['id']}", params={"user_id": "wrong"}
    )
    assert resp.status_code == 403
    assert resp.json() == {"error": "forbidden"}


# ===========================================================================
# DELETE Happy Path
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_file(client: AsyncClient):
    """DELETE /files/{id}?user_id=test_user with valid id returns 204."""
    uploaded = await _upload_file(client)

    resp = await client.delete(
        f"/files/{uploaded['id']}", params={"user_id": "test_user"}
    )
    assert resp.status_code == 204
    assert resp.content == b""


@pytest.mark.asyncio
async def test_delete_file_twice(client: AsyncClient):
    """DELETE same file twice: first 204, second 404."""
    uploaded = await _upload_file(client)
    file_id = uploaded["id"]

    resp1 = await client.delete(f"/files/{file_id}", params={"user_id": "test_user"})
    assert resp1.status_code == 204

    resp2 = await client.delete(f"/files/{file_id}", params={"user_id": "test_user"})
    assert resp2.status_code == 404
    assert resp2.json() == {"error": "not found"}


@pytest.mark.asyncio
async def test_delete_file_removes_from_disk(client: AsyncClient, _setup_db):
    """After delete, the stored file no longer exists on disk."""
    uploaded = await _upload_file(client)
    file_id = uploaded["id"]

    # Confirm file exists on disk first
    resp = await client.get(f"/files/{file_id}")
    stored_path = resp.json().get("stored_path")
    # Since stored_path isn't in the response schema, check the upload dir
    from app.config import get_settings
    settings = get_settings()
    upload_dir = settings.UPLOAD_DIR
    files_before = os.listdir(upload_dir)
    assert len(files_before) == 1

    # Delete
    resp = await client.delete(f"/files/{file_id}", params={"user_id": "test_user"})
    assert resp.status_code == 204

    # Verify file is gone from disk
    files_after = os.listdir(upload_dir)
    assert len(files_after) == 0

    # Verify file is gone from DB
    resp = await client.get(f"/files/{file_id}")
    assert resp.status_code == 404


# ===========================================================================
# Signing and Download
# ===========================================================================


@pytest.mark.asyncio
async def test_sign_file(client: AsyncClient):
    """POST /files/{id}/sign with valid owner returns 201 SignedUrlResponse."""
    uploaded = await _upload_file(client)
    data = await _sign_file(client, uploaded["id"])
    assert "download_url" in data
    assert data["download_url"].startswith("/download?token=")
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_sign_file_wrong_user(client: AsyncClient):
    """POST /files/{id}/sign with non-owner returns 403."""
    uploaded = await _upload_file(client, user_id="owner")

    resp = await client.post(
        f"/files/{uploaded['id']}/sign",
        json={"user_id": "intruder", "ttl_seconds": 3600},
    )
    assert resp.status_code == 403
    assert resp.json() == {"error": "forbidden"}


@pytest.mark.asyncio
async def test_sign_file_not_found(client: AsyncClient):
    """POST /files/{fake_id}/sign returns 404."""
    resp = await client.post(
        f"/files/{FAKE_UUID}/sign",
        json={"user_id": "test_user", "ttl_seconds": 3600},
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "not found"}


@pytest.mark.asyncio
async def test_sign_file_invalid_ttl(client: AsyncClient):
    """POST /files/{id}/sign with ttl_seconds below 60 returns 422."""
    uploaded = await _upload_file(client)

    resp = await client.post(
        f"/files/{uploaded['id']}/sign",
        json={"user_id": "test_user", "ttl_seconds": 10},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_download_valid_token(client: AsyncClient):
    """Upload → sign → GET /download?token=... returns 200 with file bytes."""
    content = b"download me!"
    uploaded = await _upload_file(client, content=content, filename="dl.txt")
    signed = await _sign_file(client, uploaded["id"])

    resp = await client.get(signed["download_url"])
    assert resp.status_code == 200
    assert resp.content == content
    assert resp.headers["content-type"] == "text/plain; charset=utf-8"
    assert 'filename="dl.txt"' in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_download_tampered_token(client: AsyncClient):
    """Altering the token string returns 403 invalid signature."""
    uploaded = await _upload_file(client)
    signed = await _sign_file(client, uploaded["id"])

    # Tamper with the token by flipping a character
    url = signed["download_url"]
    token = url.split("token=")[1]
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    resp = await client.get(f"/download?token={tampered}")
    assert resp.status_code == 403
    assert resp.json() == {"error": "forbidden"}


@pytest.mark.asyncio
async def test_download_expired_token(client: AsyncClient):
    """Generate token with ttl_seconds=60, patch time forward, then download → 410."""
    from unittest.mock import patch
    from datetime import datetime, timezone, timedelta

    uploaded = await _upload_file(client)

    # Generate with minimum TTL
    signed = await _sign_file(client, uploaded["id"], ttl_seconds=60)

    # Patch datetime.now to return a time 120 seconds in the future
    future_time = datetime.now(timezone.utc) + timedelta(seconds=120)
    with patch("app.services.signing_service.datetime") as mock_dt:
        mock_dt.now.return_value = future_time
        mock_dt.fromtimestamp = datetime.fromtimestamp
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        resp = await client.get(signed["download_url"])

    assert resp.status_code == 410
    assert resp.json() == {"error": "link expired"}


@pytest.mark.asyncio
async def test_download_deleted_file(client: AsyncClient):
    """Upload → sign → delete file → download returns 404."""
    uploaded = await _upload_file(client)
    signed = await _sign_file(client, uploaded["id"])

    # Delete the file
    resp = await client.delete(
        f"/files/{uploaded['id']}", params={"user_id": "test_user"}
    )
    assert resp.status_code == 204

    # Try to download — file no longer in DB
    resp = await client.get(signed["download_url"])
    assert resp.status_code == 404
    assert resp.json() == {"error": "not found"}


# ===========================================================================
# Audit
# ===========================================================================


@pytest.mark.asyncio
async def test_audit_log_created_on_sign(client: AsyncClient):
    """Sign a file, then GET /files/{id}/audit returns 1 audit event."""
    uploaded = await _upload_file(client)
    await _sign_file(client, uploaded["id"])

    resp = await client.get(
        f"/files/{uploaded['id']}/audit",
        params={"user_id": "test_user"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    event = data["items"][0]
    assert event["file_id"] == uploaded["id"]
    assert event["client_ip"] is not None


@pytest.mark.asyncio
async def test_audit_log_wrong_user(client: AsyncClient):
    """GET /files/{id}/audit?user_id=wrong returns 403."""
    uploaded = await _upload_file(client, user_id="owner")

    resp = await client.get(
        f"/files/{uploaded['id']}/audit",
        params={"user_id": "wrong"},
    )
    assert resp.status_code == 403
    assert resp.json() == {"error": "forbidden"}


# ===========================================================================
# Edge Cases
# ===========================================================================


@pytest.mark.asyncio
async def test_list_files_pagination(client: AsyncClient):
    """Pagination: page_size=1 after uploading 2 files returns total: 2, 1 item."""
    await _upload_file(client, filename="a.txt", content=b"aaa")
    await _upload_file(client, filename="b.txt", content=b"bbb")

    resp = await client.get(
        "/files", params={"user_id": "test_user", "page": 1, "page_size": 1}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 1
    assert data["page"] == 1
    assert data["page_size"] == 1


@pytest.mark.asyncio
async def test_get_file_invalid_uuid_format(client: AsyncClient):
    """GET /files/not-a-uuid returns 422."""
    resp = await client.get("/files/not-a-uuid")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sign_creates_audit_with_client_ip(client: AsyncClient):
    """After signing, audit event has a non-empty client_ip."""
    uploaded = await _upload_file(client)
    await _sign_file(client, uploaded["id"])

    resp = await client.get(
        f"/files/{uploaded['id']}/audit",
        params={"user_id": "test_user"},
    )
    assert resp.status_code == 200
    event = resp.json()["items"][0]
    assert event["client_ip"] != ""
    assert event["client_ip"] is not None


# ===========================================================================
# Additional Edge Cases (from code review)
# ===========================================================================


@pytest.mark.asyncio
async def test_upload_preserves_original_filename(client: AsyncClient):
    """Upload with a specific filename — the response contains the original name,
    not the UUID-based stored name. Ensures user-facing metadata stays correct."""
    data = await _upload_file(client, filename="my-report.csv", content=b"a,b,c")
    assert data["filename"] == "my-report.csv"


@pytest.mark.asyncio
async def test_upload_large_content_type(client: AsyncClient):
    """Upload with application/octet-stream content type is preserved.
    Ensures non-text MIME types are stored and returned correctly."""
    data = await _upload_file(
        client,
        filename="data.bin",
        content=b"\x00\x01\x02",
        content_type="application/octet-stream",
    )
    assert data["content_type"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_list_files_page_beyond_total(client: AsyncClient):
    """Requesting a page beyond total results returns empty items but correct total.
    Ensures pagination doesn't error on out-of-range pages."""
    await _upload_file(client)

    resp = await client.get(
        "/files", params={"user_id": "test_user", "page": 999, "page_size": 10}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"] == []
    assert data["page"] == 999


@pytest.mark.asyncio
async def test_sign_file_custom_ttl(client: AsyncClient):
    """Sign with a non-default TTL (86400s). Verifies the signing service
    accepts the full range of valid TTLs and the download URL still works."""
    uploaded = await _upload_file(client)

    resp = await client.post(
        f"/files/{uploaded['id']}/sign",
        json={"user_id": "test_user", "ttl_seconds": 86400},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["download_url"].startswith("/download?token=")


@pytest.mark.asyncio
async def test_sign_file_ttl_too_large(client: AsyncClient):
    """TTL above 86400 is rejected with 422. Ensures the upper bound
    validation on SignRequest.ttl_seconds is enforced."""
    uploaded = await _upload_file(client)

    resp = await client.post(
        f"/files/{uploaded['id']}/sign",
        json={"user_id": "test_user", "ttl_seconds": 100000},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_download_missing_token_param(client: AsyncClient):
    """GET /download with no token query param returns 422.
    Ensures the required query parameter is validated."""
    resp = await client.get("/download")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_multiple_signs_create_multiple_audit_events(client: AsyncClient):
    """Signing a file 3 times creates 3 audit events.
    Validates audit is recorded per-sign, not deduplicated."""
    uploaded = await _upload_file(client)
    for _ in range(3):
        await _sign_file(client, uploaded["id"])

    resp = await client.get(
        f"/files/{uploaded['id']}/audit",
        params={"user_id": "test_user"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


@pytest.mark.asyncio
async def test_delete_then_get_returns_404(client: AsyncClient):
    """After deleting a file, GET /files/{id} returns 404.
    Confirms the DB record is actually removed, not just soft-deleted."""
    uploaded = await _upload_file(client)
    file_id = uploaded["id"]

    await client.delete(f"/files/{file_id}", params={"user_id": "test_user"})

    resp = await client.get(f"/files/{file_id}")
    assert resp.status_code == 404
    assert resp.json() == {"error": "not found"}


@pytest.mark.asyncio
async def test_delete_then_list_excludes_file(client: AsyncClient):
    """After deleting a file, listing no longer includes it.
    Ensures delete is reflected in list queries immediately."""
    uploaded = await _upload_file(client)
    await client.delete(
        f"/files/{uploaded['id']}", params={"user_id": "test_user"}
    )

    resp = await client.get("/files", params={"user_id": "test_user"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []
