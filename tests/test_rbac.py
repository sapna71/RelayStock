import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Membership
from tests.helpers import API, bearer, join, register, role_id


async def test_tenant_isolation_between_organizations(client):
    a, b = await register(client, org="A"), await register(client, org="B")
    a_members = (await client.get(f"{API}/members", headers=bearer(a))).json()
    b_members = (await client.get(f"{API}/members", headers=bearer(b))).json()
    assert [m["email"] for m in a_members] == [a["email"]] and [m["email"] for m in b_members] == [b["email"]]
    # A cannot touch B's membership or use B's role
    assert (await client.patch(f"{API}/members/{b_members[0]['id']}", headers=bearer(a),
                               json={"role_id": await role_id(client, a, "Inventory Analyst")})).status_code == 404
    assert (await client.delete(f"{API}/members/{b_members[0]['id']}", headers=bearer(a))).status_code == 404
    b_role = await role_id(client, b, "Inventory Analyst")
    inv = await client.post(f"{API}/members/invitations", headers=bearer(a),
                            json={"email": "x@example.com", "role_id": b_role})
    assert inv.status_code == 404 and inv.json()["code"] == "role_not_found"
    assert (await client.put(f"{API}/roles/{b_role}/permissions", headers=bearer(a),
                             json={"permissions": []})).status_code == 404
    assert {r["name"] for r in (await client.get(f"{API}/roles", headers=bearer(a))).json()} == {
        "Operations Director", "Warehouse Manager", "Procurement Lead", "Inventory Analyst"}


async def test_database_rejects_cross_tenant_role_assignment(client, session):
    a, b = await register(client, org="A"), await register(client, org="B")
    b_role = await role_id(client, b, "Inventory Analyst")
    org_a = a["organization_id"]
    session.add(Membership(organization_id=org_a, user_id=b["user"]["id"], role_id=b_role))
    with pytest.raises(IntegrityError):
        await session.flush()  # composite FK (organization_id, role_id) -> roles(organization_id, id)
    await session.rollback()


async def test_permissions_are_enforced_per_role(client):
    owner = await register(client)
    analyst = await join(client, owner, "Inventory Analyst")
    h = bearer(analyst)
    assert (await client.get(f"{API}/members", headers=h)).status_code == 200  # directory is visible to members
    denied = await client.post(f"{API}/members/invitations", headers=h,
                               json={"email": "n@example.com", "role_id": await role_id(client, owner, "Warehouse Manager")})
    assert denied.status_code == 403 and denied.json()["code"] == "missing_permission"
    assert (await client.get(f"{API}/audit-logs", headers=h)).status_code == 403
    assert (await client.patch(f"{API}/orgs/current", headers=h, json={"name": "Hijacked"})).status_code == 403
    assert (await client.get(f"{API}/audit-logs", headers=bearer(owner))).status_code == 200


async def test_role_edits_take_effect_immediately_on_existing_tokens(client):
    owner = await register(client)
    analyst = await join(client, owner, "Inventory Analyst")
    target = await role_id(client, owner, "Inventory Analyst")
    body = {"email": "later@example.com", "role_id": await role_id(client, owner, "Warehouse Manager")}
    assert (await client.post(f"{API}/members/invitations", headers=bearer(analyst), json=body)).status_code == 403
    r = await client.put(f"{API}/roles/{target}/permissions", headers=bearer(owner),
                         json={"permissions": ["inventory.view", "team.manage"]})
    assert r.status_code == 200 and r.json()["permissions"] == ["inventory.view", "team.manage"]
    # The Analyst now holds team.manage, but the Warehouse Manager role carries permissions they lack.
    blocked = await client.post(f"{API}/members/invitations", headers=bearer(analyst), json=body)
    assert blocked.status_code == 403 and blocked.json()["code"] == "privilege_escalation"
    ok = await client.post(f"{API}/members/invitations", headers=bearer(analyst),
                           json={**body, "role_id": target})
    assert ok.status_code == 201


async def test_director_role_is_locked_and_escalation_is_blocked(client):
    owner = await register(client)
    owner_role = await role_id(client, owner, "Operations Director")
    locked = await client.put(f"{API}/roles/{owner_role}/permissions", headers=bearer(owner), json={"permissions": []})
    assert locked.status_code == 409 and locked.json()["code"] == "role_locked"
    assert (await client.put(f"{API}/roles/{await role_id(client, owner, 'Inventory Analyst')}/permissions",
                             headers=bearer(owner), json={"permissions": ["not.real"]})).status_code == 422

    proc_role = await role_id(client, owner, "Procurement Lead")
    await client.put(f"{API}/roles/{proc_role}/permissions", headers=bearer(owner),
                     json={"permissions": ["inventory.view", "procurement.approve", "team.manage"]})
    proc = await join(client, owner, "Procurement Lead")
    analyst_role = await role_id(client, owner, "Inventory Analyst")
    esc = await client.put(f"{API}/roles/{analyst_role}/permissions", headers=bearer(proc),
                           json={"permissions": ["inventory.view", "settings.edit"]})
    assert esc.status_code == 403 and esc.json()["code"] == "privilege_escalation"
    fine = await client.put(f"{API}/roles/{analyst_role}/permissions", headers=bearer(proc),
                            json={"permissions": ["inventory.view", "procurement.approve"]})
    assert fine.status_code == 200
    # a non-Director cannot hand out the Director role
    own = await client.post(f"{API}/members/invitations", headers=bearer(proc),
                            json={"email": "boss@example.com", "role_id": owner_role})
    assert own.status_code == 403 and own.json()["code"] == "owner_only"


async def test_permission_catalog_and_role_listing(client):
    owner = await register(client)
    cat = (await client.get(f"{API}/permissions", headers=bearer(owner))).json()
    assert {c["code"] for c in cat} >= {"inventory.view", "team.manage", "audit.view"}
    roles = {r["name"]: r for r in (await client.get(f"{API}/roles", headers=bearer(owner))).json()}
    assert roles["Operations Director"]["member_count"] == 1 and len(roles["Operations Director"]["permissions"]) == 9
    assert roles["Warehouse Manager"]["permissions"] == [
        "analytics.view", "inventory.adjust", "inventory.view", "orders.manage", "transfers.manage"]