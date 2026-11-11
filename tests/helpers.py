from alembic.config import Config

from app.core.config import BACKEND_DIR


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))  # configparser escaping
    return cfg


# ---- API helpers used by the Phase 2+ tests ----
import uuid

PASSWORD = "correct horse battery"
API = "/api/v1"


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def register(client, *, email: str | None = None, password: str = PASSWORD, org: str = "Acme",
                   name: str = "Ada Lovelace") -> dict:
    email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    r = await client.post(f"{API}/auth/register", json={
        "email": email, "password": password, "full_name": name, "organization_name": org})
    assert r.status_code == 201, r.text
    return {**r.json(), "email": email, "password": password}


async def role_id(client, tokens: dict, name: str) -> str:
    r = await client.get(f"{API}/roles", headers=bearer(tokens))
    assert r.status_code == 200, r.text
    return next(x["id"] for x in r.json() if x["name"] == name)


async def join(client, owner: dict, role_name: str, password: str = PASSWORD) -> dict:
    """Invite a brand-new user into the owner's organization and accept as them."""
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    inv = await client.post(f"{API}/members/invitations", headers=bearer(owner),
                            json={"email": email, "role_id": await role_id(client, owner, role_name)})
    assert inv.status_code == 201, inv.text
    r = await client.post(f"{API}/auth/accept-invitation", json={
        "token": inv.json()["token"], "password": password, "full_name": f"{role_name} Person"})
    assert r.status_code == 201, r.text
    return {**r.json(), "email": email, "password": password}