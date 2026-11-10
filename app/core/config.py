from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent

_ASYNC_DRIVER = "postgresql+asyncpg"
_ACCEPTED_DRIVERS = {
    "postgresql",
    "postgres",
    "postgresql+psycopg2",
    "postgresql+psycopg",
    "postgresql+asyncpg",
}


def normalize_database_url(raw: str) -> str:
    """Force the asyncpg driver and translate libpq-style options.

    A plain ``postgresql://`` URL (what most tools generate) becomes
    ``postgresql+asyncpg://``. asyncpg has no ``sslmode`` parameter, it uses ``ssl``.
    """
    url = make_url(raw)
    if url.drivername not in _ACCEPTED_DRIVERS:
        raise ValueError(f"Unsupported database driver: {url.drivername!r}. Use PostgreSQL.")
    url = url.set(drivername=_ASYNC_DRIVER)
    query = dict(url.query)
    if "sslmode" in query:
        query["ssl"] = query.pop("sslmode")
        url = url.set(query=query)
    return url.render_as_string(hide_password=False)


class Settings(BaseSettings):
    # Root .env first, backend/.env second (later files win). Unknown keys are ignored.
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "RelayStock API"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    test_database_url: str | None = None
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    db_pool_size: int = 10
    db_max_overflow: int = 10

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _normalize_url(cls, v: str | None) -> str | None:
        return None if v is None else normalize_database_url(v)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def resolved_test_database_url(self) -> str:
        if self.test_database_url:
            return self.test_database_url
        return (
            make_url(self.database_url)
            .set(database="relaystock_test")
            .render_as_string(hide_password=False)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]