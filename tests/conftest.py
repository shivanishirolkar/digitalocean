"""Shared test fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture()
async def client():
    """Yield a function-scoped async HTTP client wired to the FastAPI app.

    Uses httpx's ASGITransport so requests never leave the process.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
