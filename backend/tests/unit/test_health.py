from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.main import create_app


@pytest.mark.usefixtures("app_env")
async def test_health_stays_available_when_database_is_unreachable() -> None:
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        health = await client.get("/health")
        ready = await client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert UUID(health.headers["X-Request-ID"]).version == 4
    assert ready.status_code == 503
    assert ready.json()["error"]["code"] == "NOT_READY"


@pytest.mark.usefixtures("app_env")
def test_app_rejects_missing_required_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET")

    with pytest.raises(ValidationError, match="jwt_secret"):
        create_app()
