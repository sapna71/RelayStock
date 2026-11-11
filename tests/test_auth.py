import asyncio
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select, update

from app.core.config import get_settings
from app.models import User
from tests.helpers import API, PASSWORD, bearer, register


async def test_register_login_me(client):
    t = await register(client, org="Acme Corp")
    assert t["token_type"] == "bearer" and t["memberships"][0]["role_name"] == "Operations Director"
    me = await client.get(f"{API}/auth/me", headers=bearer(t))
    assert me.status_code == 200
    body = me.json()
    assert body["organization"]["name"] == "Acme Corp" and body["role"]["is_owner"] is True
    assert len(body["permissions"]) == 9
    r = await client.post(f"{API}/auth/login", json={"email": t["email"].upper(), "password": PASSWORD})
    assert r.status_code == 200 and r.json()["user"]["email"] == t["email"]


async def test_register_validation_and_duplicate_email(client):
    base = {"email": "dup@example.com", "password": PASSWORD, "full_name": "Dup", "organization_name": "Org"}
    assert (await client.post(f"{API}/auth/register", json={**base, "password": "short"})).status_code == 422
    assert (await client.post(f"{API}/auth/register", json={**base, "email": "not-an-email"})).status_code == 422
    first = await client.post(f"{API}/auth/register", json={**base, "email": "Dup-Case@Example.com"})
    assert first.status_code == 201
    again = await client.post(f"{API}/auth/register", json={**base, "email": "dup-case@example.com"})
    assert again.status_code == 409 and again.json()["code"] == "email_taken"


async def test_bad_credentials_look_identical(client):
    t = await register(client)
    wrong = await client.post(f"{API}/auth/login", json={"email": t["email"], "password": "wrong-password"})
    unknown = await client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_lockout_after_repeated_failures_then_recovery(client, session):
    t = await register(client)
    for _ in range(get_settings().max_failed_logins):
        r = await client.post(f"{API}/auth/login", json={"email": t["email"], "password": "wrong-password"})
        assert r.status_code == 401
    locked = await client.post(f"{API}/auth/login", json={"email": t["email"], "password": PASSWORD})
    assert locked.status_code == 429 and locked.json()["code"] == "account_locked"
    await session.execute(update(User).where(User.email == t["email"])
                          .values(locked_until=datetime.now(timezone.utc) - timedelta(minutes=1)))
    await session.commit()
    ok = await client.post(f"{API}/auth/login", json={"email": t["email"], "password": PASSWORD})
    assert ok.status_code == 200


async def test_inactive_user_cannot_login_or_use_token(client, session):
    t = await register(client)
    await session.execute(update(User).where(User.email == t["email"]).values(is_active=False))
    await session.commit()
    assert (await client.post(f"{API}/auth/login", json={"email": t["email"], "password": PASSWORD})).status_code == 401
    assert (await client.get(f"{API}/auth/me", headers=bearer(t))).status_code == 401


async def test_refresh_rotates_and_reuse_revokes_the_family(client):
    t = await register(client)
    r1 = await client.post(f"{API}/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r1.status_code == 200
    new = r1.json()
    assert new["refresh_token"] != t["refresh_token"]
    replay = await client.post(f"{API}/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert replay.status_code == 401 and replay.json()["code"] == "refresh_token_reused"
    killed = await client.post(f"{API}/auth/refresh", json={"refresh_token": new["refresh_token"]})
    assert killed.status_code == 401


async def test_concurrent_refresh_only_one_wins(client):
    t = await register(client)
    results = await asyncio.gather(*[client.post(f"{API}/auth/refresh", json={"refresh_token": t["refresh_token"]})
                                     for _ in range(2)])
    assert sorted(r.status_code for r in results) == [200, 401]


async def test_logout_revokes_refresh_token(client):
    t = await register(client)
    assert (await client.post(f"{API}/auth/logout", json={"refresh_token": t["refresh_token"]})).status_code == 204
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": t["refresh_token"]})).status_code == 401
    assert (await client.post(f"{API}/auth/logout", json={"refresh_token": "x" * 40})).status_code == 204


async def test_missing_malformed_and_expired_access_tokens(client):
    t = await register(client)
    assert (await client.get(f"{API}/auth/me")).status_code == 401
    assert (await client.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage"})).status_code == 401
    s = get_settings()
    now = datetime.now(timezone.utc)
    claims = jwt.decode(t["access_token"], options={"verify_signature": False})
    expired = jwt.encode({**claims, "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
                         s.jwt_secret, algorithm="HS256")
    r = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"