import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.client import mount_client
from app.main import create_app


@pytest.mark.usefixtures("app_env")
async def test_serves_client_pages_and_socket_io_asset() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path, element in (
            ("/", "account-form"),
            ("/lobby", "page-title"),
            ("/rooms", "mine"),
            ("/account", "password-form"),
            ("/rooms/join", "join-form"),
            ("/rooms/create", "create-form"),
            ("/room", "enter-form"),
        ):
            response = await client.get(path)
            assert response.status_code == 200
            assert f'id="{element}"' in response.text
        asset = await client.get("/client/vendor/socket.io.min.js")
        assert asset.status_code == 200
        assert "Socket.IO" in asset.text


async def test_workspace_routes_have_separate_content() -> None:
    app = FastAPI()
    mount_client(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path, own, excluded in (
            (
                "/lobby",
                'href="/rooms/join"',
                ('id="mine"', 'id="profile"', 'id="join-form"', 'id="create-form"'),
            ),
            ("/rooms", 'id="mine"', ('id="profile"', 'id="join-form"', 'id="create-form"')),
            ("/account", 'id="profile"', ('id="mine"', 'id="join-form"', 'id="create-form"')),
            ("/rooms/join", 'id="join-form"', ('id="mine"', 'id="profile"', 'id="create-form"')),
            ("/rooms/create", 'id="create-form"', ('id="mine"', 'id="profile"', 'id="join-form"')),
        ):
            response = await client.get(path)
            assert response.status_code == 200
            assert own in response.text
            assert not any(fragment in response.text for fragment in excluded)
            assert 'href="#rooms-sidebar"' not in response.text
            assert 'href="#account-sidebar"' not in response.text


@pytest.mark.parametrize("dev", [True, False])
async def test_styleguide_is_development_only(dev: bool) -> None:
    app = FastAPI()
    mount_client(app, dev=dev)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/styleguide", "/client/styleguide.html", "/client/./styleguide.html"):
            response = await client.get(path)
            assert response.status_code == (200 if dev else 404)
            if dev:
                assert "data-styleguide" in response.text
                assert "script-src 'self'" in response.text
                assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        if not dev:
            for path in ("/client//styleguide.html", "/client/%73tyleguide.html"):
                assert (await client.get(path)).status_code == 404
