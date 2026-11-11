from tests.helpers import API, bearer, join, register


async def test_create_second_org_and_switch_via_refresh(client):
    t = await register(client, org="First")
    created = await client.post(f"{API}/orgs", headers=bearer(t), json={"name": "Second Co", "currency": "EUR"})
    assert created.status_code == 201 and created.json()["currency"] == "EUR"
    orgs = (await client.get(f"{API}/orgs", headers=bearer(t))).json()
    assert [o["organization_name"] for o in orgs] == ["First", "Second Co"]
    sw = await client.post(f"{API}/auth/refresh", json={"refresh_token": t["refresh_token"], "organization_id": created.json()["id"]})
    assert sw.status_code == 200 and sw.json()["organization_id"] == created.json()["id"]
    me = await client.get(f"{API}/auth/me", headers=bearer(sw.json()))
    assert me.json()["organization"]["name"] == "Second Co"
    # the old access token still points at the first org
    assert (await client.get(f"{API}/auth/me", headers=bearer(t))).json()["organization"]["name"] == "First"


async def test_switching_to_foreign_org_is_forbidden_and_keeps_token_valid(client):
    a, b = await register(client), await register(client)
    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": a["refresh_token"], "organization_id": b["organization_id"]})
    assert r.status_code == 403 and r.json()["code"] == "not_a_member"
    ok = await client.post(f"{API}/auth/refresh", json={"refresh_token": a["refresh_token"]})
    assert ok.status_code == 200
    login = await client.post(f"{API}/auth/login", json={"email": a["email"], "password": a["password"], "organization_id": b["organization_id"]})
    assert login.status_code == 403


async def test_update_org_settings_with_validation_and_audit(client):
    owner = await register(client)
    ok = await client.patch(f"{API}/orgs/current", headers=bearer(owner),
                            json={"name": "Renamed", "timezone": "Europe/Amsterdam", "currency": "EUR", "fiscal_year_start_month": 4})
    assert ok.status_code == 200 and ok.json()["fiscal_year_start_month"] == 4
    for bad in ({"currency": "usd"}, {"fiscal_year_start_month": 13}, {"timezone": "bad zone!"}, {}):
        assert (await client.patch(f"{API}/orgs/current", headers=bearer(owner), json=bad)).status_code == 422
    logs = (await client.get(f"{API}/audit-logs?action=org.update", headers=bearer(owner))).json()
    assert logs["total"] == 1 and logs["items"][0]["detail"]["name"] == {"from": "Acme", "to": "Renamed"}


async def test_settings_edit_permission_required(client):
    owner = await register(client)
    analyst = await join(client, owner, "Inventory Analyst")
    assert (await client.patch(f"{API}/orgs/current", headers=bearer(analyst), json={"name": "Nope"})).status_code == 403
    assert (await client.get(f"{API}/orgs/current", headers=bearer(analyst))).json()["name"] == "Acme"