"""Integration tests for database table existence."""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_files_table_exists(db_session):
    """The 'files' table must exist in the test database."""
    result = await db_session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'files'"
        )
    )
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_audit_table_exists(db_session):
    """The 'signed_url_audit' table must exist in the test database."""
    result = await db_session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'signed_url_audit'"
        )
    )
    assert result.scalar() == 1
