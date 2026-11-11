import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.models import Invitation
from tests.helpers import API, PASSWORD, bearer, join, register, role_id


async def test_invite_and_accept_new_user(client):
    owner = await register(client)
    rid = await role_id(client, owner, "Warehouse Manager")
    inv = await client.post(f"{API}/members/invitations", headers=bearer(owner), json={"email": "New@Example.com", "role_id": rid})
    assert inv.status_code == 201 and inv.json()["email"] == "new@example.com"
    token = inv.json()["token"]
    dup = await client.post(f"{API}/members/invitations", headers=bearer(owner), json={"email": "new@example.com", "role_id": rid})
    assert dup.status_code == 409 and dup.json()["code"] == "invitation_pending"
    acc = await client.post(f"{API}/auth/accept-invitation", json={"token": token, "password": PASSWORD, "full_name": "New Hire"})
    assert acc.status_code == 201 and acc.json()["memberships"][0]["role_name"] == "Warehouse Manager"
    again = await client.post(f"{API}/auth/accept-invitation", json={"token": token, "password": PASSWORD, "full_name": "X"})
    assert again.status_code == 400 and again.json()["code"] == "invalid_invitation"
    members = (await client.get(f"{API}/members", headers=bearer(owner))).json()
    assert {m["email"] for m in members} == {owner["email"], "new@example.com"}
    again_invite = await client.post(f"{API}/members/invitations", headers=bearer(owner), json={"email": "new@example.com", "role_id": rid})
    assert again_invite.status_code == 409 and again_invite.json()["code"] == "already_member"


async def test_expired_invitation_is_rejected_and_can_be_reissued(client, session):
    owner = await register(client)
    rid = await role_id(client, owner, "Inventory Analyst")
    inv = await client.post(f"{API}/members/invitations", headers=bearer(owner), json={"email": "late@example.com", "role_id": rid})
    await session.execute(update(Invitation).where(Invitation.email == "late@example.com")
                          .values(expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
    await session.commit()
    r = await client.post(f"{API}/auth/accept-invitation", json={"token": inv.json()["token"], "password": PASSWORD, "full_name": "L"})
    assert r.status_code == 400
    fresh = await client.post(f"{API}/members/invitations", headers=bearer(owner), json={"email": "late@example.com", "role_id": rid})
    assert fresh.status_code == 201


async def test_existing_user_joins_second_org_with_their_password(client):
    org_a, org_b = await register(client, org="A"), await register(client, org="B")
    rid = await role_id(client, org_b, "Procurement Lead")
    inv = await client.post(f"{API}/members/invitations", headers=bearer(org_b), json={"email": org_a["email"], "role_id": rid})
    bad = await client.post(f"{API}/auth/accept-invitation", json={"token": inv.json()["token"], "password": "wrong-password-1", "full_name": "A"})
    assert bad.status_code == 401
    ok = await client.post(f"{API}/auth/accept-invitation", json={"token": inv.json()["token"], "password": org_a["password"], "full_name": "A"})
    assert ok.status_code == 201 and len(ok.json()["memberships"]) == 2


async def test_change_role_and_remove_member(client):
    owner = await register(client)
    member = await join(client, owner, "Inventory Analyst")
    mid = next(m["id"] for m in (await client.get(f"{API}/members", headers=bearer(owner))).json() if m["email"] == member["email"])
    wm = await role_id(client, owner, "Warehouse Manager")
    r = await client.patch(f"{API}/members/{mid}", headers=bearer(owner), json={"role_id": wm})
    assert r.status_code == 200 and r.json()["role_name"] == "Warehouse Manager"
    assert (await client.delete(f"{API}/members/{mid}", headers=bearer(owner))).status_code == 204
    # the removed person's still-unexpired token stops working at once
    assert (await client.get(f"{API}/auth/me", headers=bearer(member))).status_code == 401


async def test_last_director_cannot_be_demoted_or_removed(client):
    owner = await register(client)
    mid = (await client.get(f"{API}/members", headers=bearer(owner))).json()[0]["id"]
    demote = await client.patch(f"{API}/members/{mid}", headers=bearer(owner),
                                json={"role_id": await role_id(client, owner, "Inventory Analyst")})
    assert demote.status_code == 409 and demote.json()["code"] == "last_owner"
    remove = await client.delete(f"{API}/members/{mid}", headers=bearer(owner))
    assert remove.status_code == 409 and remove.json()["code"] == "last_owner"


async def test_concurrent_demotions_never_leave_zero_directors(client):
    owner = await register(client)
    second = await join(client, owner, "Operations Director")
    members = {m["email"]: m["id"] for m in (await client.get(f"{API}/members", headers=bearer(owner))).json()}
    analyst = await role_id(client, owner, "Inventory Analyst")
    # each Director tries to demote the other at the same instant
    r = await asyncio.gather(
        client.patch(f"{API}/members/{members[second['email']]}", headers=bearer(owner), json={"role_id": analyst}),
        client.patch(f"{API}/members/{members[owner['email']]}", headers=bearer(second), json={"role_id": analyst}))
    assert sorted(x.status_code for x in r) == [200, 409]
    roles = {x["name"]: x for x in (await client.get(f"{API}/roles", headers=bearer(
        owner if r[0].status_code == 409 else second))).json()}
    assert roles["Operations Director"]["member_count"] == 1


async def test_non_director_cannot_modify_a_director(client):
    owner = await register(client)
    wm_role = await role_id(client, owner, "Warehouse Manager")
    await client.put(f"{API}/roles/{wm_role}/permissions", headers=bearer(owner),
                     json={"permissions": ["inventory.view", "team.manage"]})
    manager = await join(client, owner, "Warehouse Manager")
    owner_mid = next(m["id"] for m in (await client.get(f"{API}/members", headers=bearer(manager))).json() if m["email"] == owner["email"])
    r = await client.delete(f"{API}/members/{owner_mid}", headers=bearer(manager))
    assert r.status_code == 403 and r.json()["code"] == "owner_only"