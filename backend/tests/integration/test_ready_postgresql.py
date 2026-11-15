import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import create_app


@pytest.fixture
def postgres_url(monkeypatch: pytest.MonkeyPatch, app_env: None) -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Cần TEST_DATABASE_URL trỏ đến PostgreSQL đã chạy migration.")
    monkeypatch.setenv("DATABASE_URL", url)
    return url


@pytest.fixture
def app(postgres_url: str) -> FastAPI:
    return create_app()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client,
    ):
        yield http_client


async def test_readiness_when_database_is_at_head(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_when_migration_is_missing(
    app: FastAPI, client: AsyncClient, postgres_url: str
) -> None:
    # Ẩn bảng Alembic trong riêng phiên kiểm thử, không sửa schema hay dữ liệu.
    engine = create_async_engine(
        postgres_url, connect_args={"server_settings": {"search_path": "pg_catalog"}}
    )
    app.state.engine = engine
    try:
        response = await client.get("/ready")
    finally:
        await engine.dispose()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NOT_READY"
