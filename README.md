# RelayStock backend (Phase 1: foundation)

Python 3.12, FastAPI, SQLAlchemy 2 async, asyncpg, Alembic, Pydantic v2.

## Setup (Windows PowerShell, from `F:\relaystock\backend`)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env      # skip if F:\relaystock\.env or backend\.env already has DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

`DATABASE_URL` may be `postgresql://...` or `postgresql+asyncpg://...`; it is normalised to asyncpg.
Settings load `F:\relaystock\.env` first, then `backend\.env`.

Probes: `GET /health` (liveness), `GET /ready` (runs `SELECT 1`). Docs: `/docs`. Business API lives under `/api/v1`.

## Tests

```powershell
pytest
```

Tests use a separate database, `relaystock_test` (or `TEST_DATABASE_URL`). It is created automatically when the
database user has CREATEDB; otherwise run `createdb relaystock_test` once. The suite refuses to run against any
database whose name does not end in `_test`.

## Layout

```
app/core      settings, logging          app/db       Base, mixins, async engine/session
app/api/v1    routers (health now)       app/schemas  Pydantic models
app/models    ORM models (from Phase 2)  migrations/  Alembic (async env)
```

Services (`app/services`) arrive with the first business module in Phase 2.