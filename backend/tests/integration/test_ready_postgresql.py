from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine


async def test_readiness_when_database_is_at_head(client: AsyncClient) -> None:
    response = await client.get("http://test/ready")

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
        response = await client.get("http://test/ready")
    finally:
        await engine.dispose()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NOT_READY"
