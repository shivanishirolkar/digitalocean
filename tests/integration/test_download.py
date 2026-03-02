"""End-to-end download integration tests (Step 19 — Signing Service Deep Tests).

Exercises the full upload → sign → download pipeline through the
AsyncClient, plus edge cases around content types, disk-only deletion,
multiple signed URLs, and malformed tokens.
"""

import os

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _upload(
    client: AsyncClient,
    *,
    user_id: str = "test_user",
    filename: str = "hello.txt",
    content: bytes = b"hello world",
    content_type: str = "text/plain",
) -> dict:
    """Upload a file and return parsed JSON."""
    resp = await client.post(
        "/files",
        data={"user_id": user_id},
        files={"file": (filename, content, content_type)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _sign(
    client: AsyncClient,
    file_id: str,
    *,
    user_id: str = "test_user",
    ttl_seconds: int = 3600,
) -> dict:
    """Sign a file and return parsed JSON."""
    resp = await client.post(
        f"/files/{file_id}/sign",
        json={"user_id": user_id, "ttl_seconds": ttl_seconds},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ===========================================================================
# Required Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_full_upload_sign_download_flow(client: AsyncClient):
    """Upload a file, sign it, download via the signed URL.

    Verifies downloaded bytes match original content, Content-Type matches,
    and Content-Disposition contains the original filename.
    """
    content = b"The quick brown fox jumps over the lazy dog."
    uploaded = await _upload(
        client, filename="story.txt", content=content, content_type="text/plain"
    )
    signed = await _sign(client, uploaded["id"])

    resp = await client.get(signed["download_url"])
    assert resp.status_code == 200
    assert resp.content == content
    assert "text/plain" in resp.headers["content-type"]
    assert 'filename="story.txt"' in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_download_with_various_content_types(client: AsyncClient):
    """Upload .txt, .pdf, .png files, sign and download each.

    Verifies the correct Content-Type header is returned for each.
    """
    cases = [
        ("notes.txt", b"plain text content", "text/plain"),
        ("doc.pdf", b"%PDF-fake-content", "application/pdf"),
        ("logo.png", b"\x89PNG\r\n\x1a\nfake", "image/png"),
    ]

    for filename, content, ctype in cases:
        uploaded = await _upload(
            client, filename=filename, content=content, content_type=ctype
        )
        signed = await _sign(client, uploaded["id"])
        resp = await client.get(signed["download_url"])

        assert resp.status_code == 200, f"Failed for {filename}"
        assert ctype in resp.headers["content-type"], (
            f"Expected {ctype} in content-type for {filename}, "
            f"got {resp.headers['content-type']}"
        )
        assert resp.content == content


@pytest.mark.asyncio
async def test_signed_url_works_without_api_key(client: AsyncClient):
    """Generate a signed URL, then download without X-API-Key header.

    Proves the download endpoint is public (no auth required).
    Since auth is not yet implemented, this test ensures the endpoint
    doesn't require any credential now and will remain public later.
    """
    uploaded = await _upload(client)
    signed = await _sign(client, uploaded["id"])

    # Create a fresh client without any default headers
    from httpx import ASGITransport, AsyncClient as HC
    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with HC(transport=transport, base_url="http://test") as bare_client:
        resp = await bare_client.get(signed["download_url"])
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_multiple_signed_urls_for_same_file(client: AsyncClient):
    """Sign the same file 3 times with different TTLs.

    All 3 tokens must work and 3 audit events must be recorded.
    """
    uploaded = await _upload(client)
    file_id = uploaded["id"]

    tokens = []
    for ttl in [60, 1800, 86400]:
        signed = await _sign(client, file_id, ttl_seconds=ttl)
        tokens.append(signed["download_url"])

    # All 3 tokens should work
    for url in tokens:
        resp = await client.get(url)
        assert resp.status_code == 200

    # 3 audit events recorded
    resp = await client.get(
        f"/files/{file_id}/audit", params={"user_id": "test_user"}
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


@pytest.mark.asyncio
async def test_download_after_file_deleted_from_disk_only(
    client: AsyncClient, _setup_db
):
    """Upload, sign, manually remove file from disk, then download → 404.

    The DB record still exists but the file is gone from the filesystem.
    """
    uploaded = await _upload(client)
    signed = await _sign(client, uploaded["id"])

    # Find and remove the file from disk
    from app.config import get_settings

    settings = get_settings()
    upload_dir = settings.UPLOAD_DIR
    files_on_disk = os.listdir(upload_dir)
    assert len(files_on_disk) == 1
    os.remove(os.path.join(upload_dir, files_on_disk[0]))

    # Download should fail with 404 (file not on disk)
    resp = await client.get(signed["download_url"])
    assert resp.status_code == 404


# ===========================================================================
# Edge Cases
# ===========================================================================


@pytest.mark.asyncio
async def test_download_token_with_empty_string(client: AsyncClient):
    """GET /download?token= with empty token returns 403.
    Empty string is not a valid HMAC token — should be rejected as
    malformed before any file lookup occurs."""
    resp = await client.get("/download", params={"token": ""})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_download_token_with_garbage_base64(client: AsyncClient):
    """Token that isn't valid base64 at all returns 403.
    Exercises the decode error path in verify_signed_token."""
    resp = await client.get("/download", params={"token": "not.base64!!!"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_signed_url_after_db_delete_returns_404(client: AsyncClient):
    """Upload → sign → delete via API → download returns 404.
    Confirms that deleting through the API (DB + disk) invalidates
    the signed token even though the HMAC is still cryptographically valid."""
    uploaded = await _upload(client)
    signed = await _sign(client, uploaded["id"])

    # Delete via API
    resp = await client.delete(
        f"/files/{uploaded['id']}", params={"user_id": "test_user"}
    )
    assert resp.status_code == 204

    # Token still has a valid signature, but file is gone
    resp = await client.get(signed["download_url"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_preserves_binary_content(client: AsyncClient):
    """Upload binary content and verify byte-for-byte download fidelity.
    StreamingResponse with 64KB chunks must not corrupt binary data
    or insert extra bytes."""
    binary_data = bytes(range(256)) * 100  # 25.6 KB of varied bytes
    uploaded = await _upload(
        client,
        filename="data.bin",
        content=binary_data,
        content_type="application/octet-stream",
    )
    signed = await _sign(client, uploaded["id"])

    resp = await client.get(signed["download_url"])
    assert resp.status_code == 200
    assert resp.content == binary_data
    assert "application/octet-stream" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_content_disposition_quotes_filename(client: AsyncClient):
    """Filename in Content-Disposition is properly quoted.
    Ensures filenames with spaces or special characters are handled
    correctly in the attachment header."""
    uploaded = await _upload(
        client, filename="my report (final).txt", content=b"data"
    )
    signed = await _sign(client, uploaded["id"])

    resp = await client.get(signed["download_url"])
    assert resp.status_code == 200
    assert 'filename="my report (final).txt"' in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_two_files_two_tokens_independent(client: AsyncClient):
    """Two different files with two different tokens download independently.
    Ensures signed tokens are scoped to a specific file_id and don't
    cross-contaminate."""
    f1 = await _upload(client, filename="a.txt", content=b"file-a")
    f2 = await _upload(client, filename="b.txt", content=b"file-b")

    s1 = await _sign(client, f1["id"])
    s2 = await _sign(client, f2["id"])

    r1 = await client.get(s1["download_url"])
    r2 = await client.get(s2["download_url"])

    assert r1.content == b"file-a"
    assert r2.content == b"file-b"
