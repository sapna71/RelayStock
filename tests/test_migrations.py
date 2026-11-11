import asyncio

from alembic import command
from alembic.script import ScriptDirectory
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
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert asyncio.run(_scalar(test_db_url, "SELECT version_num FROM alembic_version")) == head


def test_step_down_to_baseline_and_back(test_db_url):
    cfg = alembic_config(test_db_url)
    command.downgrade(cfg, "0001")
    assert asyncio.run(_scalar(test_db_url, "SELECT to_regclass('audit_logs')")) is None
    assert asyncio.run(_scalar(test_db_url, "SELECT count(*) FROM pg_proc WHERE proname = 'forbid_audit_mutation'")) == 0
    command.upgrade(cfg, "head")
    assert asyncio.run(_scalar(test_db_url, "SELECT to_regclass('audit_logs')")) is not None


def test_models_and_migrations_are_in_sync(test_db_url):
    """Fails if a model changed without a migration (alembic autogenerate would find a diff)."""
    command.upgrade(alembic_config(test_db_url), "head")
    command.check(alembic_config(test_db_url))