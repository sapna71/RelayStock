from httpx import ASGITransport, AsyncClient

from app.db.session import get_session
from app.main import create_app


async def test_health_is_up(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_ready_reports_database_ok(client):
    r = await client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "database": "ok"}


async def test_ready_returns_503_without_leaking_errors():
    app = create_app()

    class BrokenSession:
        async def execute(self, *a, **k):
            raise RuntimeError("secret connection string leaked")

    async def broken():
        yield BrokenSession()

    app.dependency_overrides[get_session] = broken
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "database": "error"}
    assert "secret" not in r.text


async def test_cors_allows_the_vite_dev_origin(client):
    r = await client.options("/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_unknown_route_is_404(client):
    assert (await client.get("/api/v1/nope")).status_code == 404