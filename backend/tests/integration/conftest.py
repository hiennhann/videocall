import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

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
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test/api/v1/"
        ) as http_client,
    ):
        yield http_client
