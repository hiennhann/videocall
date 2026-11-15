import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.usefixtures("app_env")
async def test_serves_client_pages_and_socket_io_asset() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path, element in (
            ("/", "account-form"),
            ("/lobby", "join-form"),
            ("/room", "enter-form"),
        ):
            response = await client.get(path)
            assert response.status_code == 200
            assert f'id="{element}"' in response.text
        asset = await client.get("/client/vendor/socket.io.min.js")
        assert asset.status_code == 200
        assert "Socket.IO" in asset.text
