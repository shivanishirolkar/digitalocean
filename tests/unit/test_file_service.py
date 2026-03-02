"""Unit tests for app.services.file_service.

Repository functions are mocked with AsyncMock — no database access.
File system operations use pytest's tmp_path fixture.
"""

import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile

from app.services import file_service


# ── helpers ────────────────────────────────────────────────────────────

def _make_settings(tmp_path, max_file_size=10_485_760):
    """Return a settings-like object pointing UPLOAD_DIR at tmp_path."""
    return SimpleNamespace(
        UPLOAD_DIR=str(tmp_path),
        MAX_FILE_SIZE=max_file_size,
    )


def _make_upload_file(content: bytes, filename="report.pdf", content_type="application/pdf"):
    """Return a minimal UploadFile backed by in-memory bytes."""
    import io
    from starlette.datastructures import Headers

    headers = Headers({"content-type": content_type})
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=headers)


def _make_file_model(
    user_id="user_42",
    file_id=None,
    stored_path="/data/uploads/fake.pdf",
):
    """Return a fake File-like object for mocking repository returns."""
    return SimpleNamespace(
        id=file_id or uuid.uuid4(),
        user_id=user_id,
        filename="report.pdf",
        stored_path=stored_path,
        size_bytes=1024,
        content_type="application/pdf",
        uploaded_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ── upload_file ────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_upload_file_success(mock_repo, tmp_path):
    """Valid file under size limit writes to disk and calls create_file."""
    settings = _make_settings(tmp_path)
    fake_file = _make_file_model(user_id="user_42")
    mock_repo.create_file = AsyncMock(return_value=fake_file)

    upload = _make_upload_file(b"hello world", filename="doc.txt", content_type="text/plain")
    result = await file_service.upload_file(AsyncMock(), "user_42", upload, settings)

    assert result is fake_file
    mock_repo.create_file.assert_awaited_once()
    # File should have been written to disk
    call_kwargs = mock_repo.create_file.call_args
    stored_path = call_kwargs.kwargs.get("stored_path") or call_kwargs[1].get("stored_path")
    assert os.path.isfile(stored_path)
    with open(stored_path, "rb") as f:
        assert f.read() == b"hello world"


@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_upload_file_too_large(mock_repo, tmp_path):
    """File exceeding MAX_FILE_SIZE raises ValueError; repo never called, no file on disk."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    settings = _make_settings(upload_dir, max_file_size=5)
    upload = _make_upload_file(b"too large content")

    with pytest.raises(ValueError, match="file too large"):
        await file_service.upload_file(AsyncMock(), "user_42", upload, settings)

    mock_repo.create_file.assert_not_called()
    assert len(os.listdir(upload_dir)) == 0


@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_upload_empty_file(mock_repo, tmp_path):
    """Empty file raises ValueError."""
    settings = _make_settings(tmp_path)
    upload = _make_upload_file(b"")

    with pytest.raises(ValueError, match="empty file"):
        await file_service.upload_file(AsyncMock(), "user_42", upload, settings)

    mock_repo.create_file.assert_not_called()


# ── get_file ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_get_file_success(mock_repo):
    """get_file returns the file when it exists."""
    fake = _make_file_model()
    mock_repo.get_file_by_id = AsyncMock(return_value=fake)

    result = await file_service.get_file(AsyncMock(), fake.id)
    assert result is fake


@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_get_file_not_found(mock_repo):
    """get_file raises ValueError when file doesn't exist."""
    mock_repo.get_file_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="file not found"):
        await file_service.get_file(AsyncMock(), uuid.uuid4())


# ── list_files ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_list_files_delegates(mock_repo):
    """list_files passes through to get_files_by_user and returns the result."""
    expected = ([_make_file_model()], 1)
    mock_repo.get_files_by_user = AsyncMock(return_value=expected)

    result = await file_service.list_files(AsyncMock(), "user_42", 1, 10)
    assert result is expected
    mock_repo.get_files_by_user.assert_awaited_once_with(
        mock_repo.get_files_by_user.call_args[0][0],  # db session
        "user_42", 1, 10,
    )


# ── delete_file ────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_delete_file_success(mock_repo, tmp_path):
    """delete_file removes from disk and calls repo delete for the owner."""
    # Create a real file on disk to verify deletion
    file_path = tmp_path / "fakefile.pdf"
    file_path.write_bytes(b"data")

    fake = _make_file_model(user_id="user_42", stored_path=str(file_path))
    mock_repo.get_file_by_id = AsyncMock(return_value=fake)
    mock_repo.delete_file = AsyncMock(return_value=True)

    await file_service.delete_file(AsyncMock(), fake.id, "user_42")

    assert not file_path.exists()
    mock_repo.delete_file.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_delete_file_not_found(mock_repo):
    """delete_file raises ValueError when file doesn't exist; repo delete not called."""
    mock_repo.get_file_by_id = AsyncMock(return_value=None)
    mock_repo.delete_file = AsyncMock()

    with pytest.raises(ValueError, match="file not found"):
        await file_service.delete_file(AsyncMock(), uuid.uuid4(), "user_42")

    mock_repo.delete_file.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_delete_file_wrong_user(mock_repo):
    """delete_file raises ValueError when user doesn't own the file; repo delete not called."""
    fake = _make_file_model(user_id="owner_99")
    mock_repo.get_file_by_id = AsyncMock(return_value=fake)
    mock_repo.delete_file = AsyncMock()

    with pytest.raises(ValueError, match="forbidden"):
        await file_service.delete_file(AsyncMock(), fake.id, "intruder")

    mock_repo.delete_file.assert_not_called()


# ── edge cases ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_upload_cleans_up_on_db_failure(mock_repo, tmp_path):
    """If the DB insert fails after writing, the file is removed from disk."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    settings = _make_settings(upload_dir)
    mock_repo.create_file = AsyncMock(side_effect=RuntimeError("db boom"))

    upload = _make_upload_file(b"some data")

    with pytest.raises(RuntimeError, match="db boom"):
        await file_service.upload_file(AsyncMock(), "user_42", upload, settings)

    # No orphan files should remain on disk
    assert len(os.listdir(upload_dir)) == 0


@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_upload_preserves_extension(mock_repo, tmp_path):
    """Stored filename uses a UUID but preserves the original file extension."""
    settings = _make_settings(tmp_path)
    mock_repo.create_file = AsyncMock(return_value=_make_file_model())

    upload = _make_upload_file(b"data", filename="photo.jpg")
    await file_service.upload_file(AsyncMock(), "user_42", upload, settings)

    call_kwargs = mock_repo.create_file.call_args
    stored_path = call_kwargs.kwargs.get("stored_path") or call_kwargs[1].get("stored_path")
    assert stored_path.endswith(".jpg")


@pytest.mark.asyncio
@patch("app.services.file_service.file_repository")
async def test_delete_file_already_gone_from_disk(mock_repo, tmp_path):
    """delete_file succeeds even if the file is already missing from disk."""
    fake = _make_file_model(user_id="user_42", stored_path=str(tmp_path / "gone.pdf"))
    mock_repo.get_file_by_id = AsyncMock(return_value=fake)
    mock_repo.delete_file = AsyncMock(return_value=True)

    # Should not raise FileNotFoundError
    await file_service.delete_file(AsyncMock(), fake.id, "user_42")
    mock_repo.delete_file.assert_awaited_once()
