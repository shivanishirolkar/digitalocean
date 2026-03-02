"""Shared test fixtures.

Uses a dedicated ``filestore_test_db`` Postgres database so tests never
touch `filestore_db`.  The DB is created once per session (if it does not
already exist).  Tables are created before and dropped after every test
to guarantee a clean schema.
"""

import re

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.database import Base, get_db
from app.main import app as fastapi_app

# Import models so Base.metadata knows about all tables
import app.models.file_model  # noqa: F401
import app.models.audit_model  # noqa: F401

settings = get_settings()

# Derive test DATABASE_URL by replacing the DB name with filestore_test_db
_TEST_DB_URL = re.sub(r"/[^/]+$", "/filestore_test_db", settings.DATABASE_URL)
# Admin URL pointing at the default 'postgres' DB (for CREATE DATABASE)
_ADMIN_DB_URL = re.sub(r"/[^/]+$", "/postgres", settings.DATABASE_URL)


# ── session-scoped: ensure the test database exists ────────────────────
@pytest.fixture(scope="session", autouse=True)
def _ensure_test_db(tmp_path_factory):  # noqa: ANN001
    """Create ``filestore_test_db`` if it doesn't already exist."""
    import asyncio

    async def _create():
        eng = create_async_engine(_ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
        async with eng.connect() as conn:
            row = await conn.execute(
                text(
                    "SELECT 1 FROM pg_database WHERE datname = 'filestore_test_db'"
                )
            )
            if row.scalar() is None:
                await conn.execute(text("CREATE DATABASE filestore_test_db"))
        await eng.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_create())
    loop.close()


# ── function-scoped: fresh engine + tables per test ────────────────────
@pytest.fixture(autouse=True)
async def _setup_db(tmp_path):
    """Create tables before each test, drop after, and point UPLOAD_DIR at tmp_path."""
    # Override UPLOAD_DIR to a temp directory for each test
    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path / "uploads")
    (tmp_path / "uploads").mkdir()

    test_engine = create_async_engine(_TEST_DB_URL, echo=False)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = _override_get_db

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield session_factory

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()
    settings.UPLOAD_DIR = original_upload_dir
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
async def db_session(_setup_db):
    """Yield a raw async DB session for repository-level tests."""
    async with _setup_db() as session:
        yield session


@pytest.fixture()
async def client():
    """Yield a function-scoped async HTTP client wired to the FastAPI app.

    Uses httpx's ASGITransport so requests never leave the process.
    The lifespan is not invoked — tables are managed by the _setup_db fixture.
    """
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
