import pytest

from app.core.config import Settings, normalize_database_url


def test_plain_postgres_url_gets_asyncpg_driver():
    out = normalize_database_url("postgresql://u:p%40ss@db:5432/relaystock_db")
    assert out == "postgresql+asyncpg://u:p%40ss@db:5432/relaystock_db"


def test_psycopg2_style_and_sslmode_are_translated():
    out = normalize_database_url("postgresql+psycopg2://u:p@h/db?sslmode=require")
    assert out.startswith("postgresql+asyncpg://") and "ssl=require" in out and "sslmode" not in out


def test_non_postgres_url_rejected():
    with pytest.raises(ValueError):
        normalize_database_url("mysql://u:p@h/db")


def test_test_database_is_derived_from_main_url():
    s = Settings(database_url="postgresql://u:p@h:5433/relaystock_db", jwt_secret="x" * 32, _env_file=None)
    assert s.resolved_test_database_url == "postgresql+asyncpg://u:p@h:5433/relaystock_test"


def test_cors_origins_parsing():
    s = Settings(database_url="postgresql://u:p@h/db", jwt_secret="x" * 32, cors_origins="http://a.test, http://b.test", _env_file=None)
    assert s.cors_origin_list == ["http://a.test", "http://b.test"]


def test_short_jwt_secret_rejected():
    with pytest.raises(ValueError):
        Settings(database_url="postgresql://u:p@h/db", jwt_secret="short", _env_file=None)