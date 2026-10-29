from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


async def test_health_and_ready(client: AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    ready = await client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "database": "ok", "redis": "ok", "storage": "disabled"}


async def test_ready_reports_unavailable_dependencies(integration_settings: Settings) -> None:
    broken = integration_settings.model_copy(
        update={
            "redis_url": "redis://127.0.0.1:1/0",
            "database_url": "postgresql://x:y@127.0.0.1:1/z",
        }
    )
    app = create_app(broken)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "service-unavailable"
    assert "base de datos" in body["detail"]
    assert "Redis" in body["detail"]
