# RelayStock backend (Phases 1-2: foundation, auth, organizations, RBAC, audit)

Python 3.12, FastAPI, SQLAlchemy 2 async, asyncpg, Alembic, Pydantic v2.

## Setup (Windows PowerShell, from `F:\relaystock\backend`)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env      # skip if F:\relaystock\.env or backend\.env already has DATABASE_URL
# REQUIRED from Phase 2: add JWT_SECRET (32+ random chars) to that .env file:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
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

## Phase 2: authentication, organizations, RBAC, audit

All routes are under `/api/v1`. Errors look like `{"detail": "...", "code": "stable_machine_code"}`.

| Route | Who | Purpose |
|---|---|---|
| `POST /auth/register` | public (`ALLOW_REGISTRATION`) | creates user + organization, user becomes Director |
| `POST /auth/login` | public | access token (15 min) + rotating refresh token (14 days) |
| `POST /auth/refresh` | refresh token | rotate tokens; send `organization_id` to switch org |
| `POST /auth/logout` | refresh token | revoke the token family |
| `POST /auth/accept-invitation` | invite token | join an organization (new or existing account) |
| `GET /auth/me` | any member | user, organization, role, permissions, memberships |
| `GET/POST /orgs`, `GET/PATCH /orgs/current` | member / `settings.edit` | organizations and settings |
| `GET /members`, `PATCH/DELETE /members/{id}`, `POST /members/invitations` | member / `team.manage` | team directory and invites |
| `GET /roles`, `PUT /roles/{id}/permissions`, `GET /permissions` | member / `team.manage` | permission matrix |
| `GET /audit-logs` | `audit.view` | paginated, filter by `action` prefix and `actor_id` |

Security model: Argon2id passwords; JWT access tokens (HS256) carrying only user and organization ids;
permissions are re-read from PostgreSQL on every request, so role edits and removals apply immediately;
refresh tokens and invitations are stored only as SHA-256 hashes; reusing a rotated refresh token revokes its
whole family; 5 failed logins lock the account for 15 minutes; every tenant query filters by the organization
in the token, and composite foreign keys stop a membership from pointing at another organization's role;
the audit log is append-only, enforced by a PostgreSQL trigger.

Invitations return a one-time `token` in the API response. Sending it by email is a Phase 8 job.