import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.usefixtures("app_env")
async def test_unexpected_errors_return_a_request_id_without_exception_details() -> None:
    app = create_app()

    @app.get("/test-error")
    async def raise_internal_error() -> None:
        raise RuntimeError("internal data")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.get("/test-error")

    assert response.status_code == 500
    assert "internal data" not in response.text
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["details"]["request_id"] == response.headers["X-Request-ID"]
