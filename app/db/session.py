from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def build_engine(url: str, **kwargs) -> AsyncEngine:
    return create_async_engine(
        url,
        connect_args={"server_settings": {"application_name": "relaystock-api"}},
        **kwargs,
    )


_settings = get_settings()
engine = build_engine(
    _settings.database_url,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_pre_ping=True,
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped session. It never commits implicitly.

    Services own transaction boundaries: they do all their work and call
    `await session.commit()` once at the end. A failure before that point is rolled back
    when the session closes, so a request can never half-commit a change.
    """
    async with SessionFactory() as session:
        yield session