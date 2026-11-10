import asyncio

from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.helpers import alembic_config

EXT_SQL = "SELECT count(*) FROM pg_extension WHERE extname IN ('pgcrypto', 'citext')"


async def _scalar(url: str, sql: str):
    eng = create_async_engine(url, poolclass=NullPool)
    try:
        async with eng.connect() as conn:
            return (await conn.execute(text(sql))).scalar()
    finally:
        await eng.dispose()


def test_baseline_downgrade_and_upgrade_cycle(test_db_url):
    # Sync on purpose: Alembic's async env.py calls asyncio.run().
    cfg = alembic_config(test_db_url)
    command.downgrade(cfg, "base")
    assert asyncio.run(_scalar(test_db_url, EXT_SQL)) == 0
    command.upgrade(cfg, "head")
    assert asyncio.run(_scalar(test_db_url, EXT_SQL)) == 2
    assert asyncio.run(_scalar(test_db_url, "SELECT version_num FROM alembic_version")) == "0001"