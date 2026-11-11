import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.helpers import API, bearer, join, register, role_id


async def test_actions_are_recorded_newest_first_and_filterable(client):
    owner = await register(client)
    member = await join(client, owner, "Inventory Analyst")
    mid = next(m["id"] for m in (await client.get(f"{API}/members", headers=bearer(owner))).json() if m["email"] == member["email"])
    await client.patch(f"{API}/members/{mid}", headers=bearer(owner), json={"role_id": await role_id(client, owner, "Warehouse Manager")})
    await client.delete(f"{API}/members/{mid}", headers=bearer(owner))
    page = (await client.get(f"{API}/audit-logs", headers=bearer(owner))).json()
    actions = [i["action"] for i in page["items"]]
    assert actions == ["member.remove", "member.role_change", "member.accept", "member.invite", "org.create"]
    assert page["items"][0]["actor_email"] == owner["email"]
    assert page["items"][1]["detail"] == {"from": "Inventory Analyst", "to": "Warehouse Manager"}
    members_only = (await client.get(f"{API}/audit-logs?action=member.", headers=bearer(owner))).json()
    assert members_only["total"] == 4
    paged = (await client.get(f"{API}/audit-logs?limit=2&offset=1", headers=bearer(owner))).json()
    assert [i["action"] for i in paged["items"]] == ["member.role_change", "member.accept"] and paged["total"] == 5
    by_actor = (await client.get(f"{API}/audit-logs?actor_id={owner['user']['id']}", headers=bearer(owner))).json()
    assert {i["actor_email"] for i in by_actor["items"]} == {owner["email"]}


async def test_audit_logs_are_tenant_scoped(client):
    a, b = await register(client, org="A"), await register(client, org="B")
    await client.patch(f"{API}/orgs/current", headers=bearer(a), json={"name": "A2"})
    logs_b = (await client.get(f"{API}/audit-logs", headers=bearer(b))).json()
    assert [i["action"] for i in logs_b["items"]] == ["org.create"]
    assert logs_b["items"][0]["detail"] == {"name": "B"}


async def test_login_is_audited(client):
    t = await register(client)
    await client.post(f"{API}/auth/login", json={"email": t["email"], "password": t["password"]})
    logs = (await client.get(f"{API}/audit-logs?action=auth.", headers=bearer(t))).json()
    assert logs["total"] == 1


@pytest.mark.parametrize("sql", [
    "UPDATE audit_logs SET action = 'tampered'",
    "DELETE FROM audit_logs",
    "TRUNCATE audit_logs",
])
async def test_database_rejects_audit_tampering(client, engine, sql):
    await register(client)  # guarantees at least one row exists
    async with engine.connect() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            await conn.execute(text(sql))
        await conn.rollback()