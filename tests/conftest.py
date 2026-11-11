import asyncio
import os
import re

# Tests need a signing secret before the app settings are first read.
os.environ.setdefault("JWT_SECRET", "test-only-secret-" + "x" * 32)

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app
from tests.helpers import alembic_config


def _connect_kwargs(url: URL, database: str) -> dict:
    kw = {"user": url.username, "password": url.password, "host": url.host,
          "port": url.port or 5432, "database": database}
    if "ssl" in url.query:
        kw["ssl"] = url.query["ssl"]
    return kw


async def _ensure_database(url: URL) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_]+", url.database or ""):
        raise RuntimeError(f"Unsafe test database name: {url.database!r}")
    conn = await asyncpg.connect(**_connect_kwargs(url, "postgres"))
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database):
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Create (if needed) and migrate the dedicated test database. Never the real one."""
    settings = get_settings()
    test_url = settings.resolved_test_database_url
    parsed, main = make_url(test_url), make_url(settings.database_url)
    if parsed.database == main.database or not parsed.database.endswith("_test"):
        pytest.exit(f"Refusing to run tests on {parsed.database!r}: it must end in '_test' "
                    "and differ from DATABASE_URL.", returncode=2)
    try:
        asyncio.run(_ensure_database(parsed))
    except Exception as exc:  # pragma: no cover - environment problem
        pytest.exit(f"Cannot create {parsed.database!r} ({exc}). Create it manually: "
                    f"createdb {parsed.database}", returncode=2)
    cfg = alembic_config(test_url)
    command.downgrade(cfg, "base")  # start every run from an empty schema
    command.upgrade(cfg, "head")
    return test_url


@pytest_asyncio.fixture
async def engine(test_db_url):
    eng = create_async_engine(test_db_url, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def client(engine):
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c