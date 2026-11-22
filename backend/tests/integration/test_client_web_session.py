import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.auth import PAGE_ACCESS_COOKIE, REFRESH_COOKIE
from app.cli import create_admin
from app.core.security import decode_access_token, issue_access_token
from app.models import User
from app.web.session import ACCESS_COOKIE as ADMIN_ACCESS_COOKIE

ORIGIN = {"Origin": "https://example.test"}
PASSWORD = "client-page-test-password"


@pytest_asyncio.fixture
async def web(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://example.test") as client,
    ):
        yield client


async def sign_in(web: AsyncClient) -> dict:
    account = {
        "email": f"page-{uuid4().hex}@example.com",
        "display_name": "Page Member",
        "password": PASSWORD,
    }
    assert (await web.post("/api/v1/auth/register", json=account)).status_code == 201
    response = await web.post(
        "/api/v1/auth/login", json={**account, "client_type": "web"}, headers=ORIGIN
    )
    assert response.status_code == 200
    return response.json()


async def test_web_assets_revalidate_after_deployment(web: AsyncClient) -> None:
    login = await web.get("/")
    assert login.headers["cache-control"] == "no-cache"
    for path in ("/client/styles.css", "/client/js/room.js", "/client/js/api.js"):
        response = await web.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        unchanged = await web.get(path, headers={"If-None-Match": response.headers["etag"]})
        assert unchanged.status_code == 304
        assert unchanged.headers["cache-control"] == "no-cache"


async def test_login_protects_html_and_logout_revokes_copied_page_cookie(web: AsyncClient) -> None:
    await sign_in(web)
    token = web.cookies.get(PAGE_ACCESS_COOKIE)
    assert token
    for path in (
        "/lobby",
        "/rooms",
        "/account",
        "/rooms/join",
        "/rooms/create",
        "/room",
        "/client/rooms.html",
    ):
        response = await web.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
    logout = await web.post("/api/v1/auth/logout", headers=ORIGIN)
    assert logout.status_code == 204
    assert web.cookies.get(PAGE_ACCESS_COOKIE) is None
    assert web.cookies.get(REFRESH_COOKIE) is None
    web.cookies.set(PAGE_ACCESS_COOKIE, token, domain="example.test", path="/")
    assert (await web.get("/rooms")).status_code == 303


async def test_page_cookie_expiry_recovers_through_existing_refresh(
    web: AsyncClient, app: FastAPI
) -> None:
    await sign_in(web)
    token = web.cookies.get(PAGE_ACCESS_COOKIE)
    identity = decode_access_token(token, app.state.auth_service.secret).identity
    expired, _ = issue_access_token(
        identity, app.state.auth_service.secret, datetime.now(UTC) - timedelta(hours=1)
    )
    web.cookies.set(PAGE_ACCESS_COOKIE, expired, domain="example.test", path="/")
    denied = await web.get("/room?code=abc-defg-hjk")
    assert denied.status_code == 303
    assert "abc-defg-hjk" in denied.headers["location"]
    refresh = await web.post("/api/v1/auth/refresh", headers=ORIGIN)
    assert refresh.status_code == 200
    cookie = next(
        value
        for value in refresh.headers.get_list("set-cookie")
        if value.startswith(PAGE_ACCESS_COOKIE + "=")
    )
    for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert flag.lower() in cookie.lower()
    assert (await web.get("/room?code=abc-defg-hjk")).status_code == 200


async def test_guest_web_login_and_logout_use_server_cookie(web: AsyncClient) -> None:
    native = await web.post("/api/v1/auth/guest", json={"display_name": "Native Guest"})
    assert native.status_code == 200 and web.cookies.get(PAGE_ACCESS_COOKIE) is None
    assert (await web.get("/lobby")).status_code == 303
    guest = await web.post(
        "/api/v1/auth/guest",
        json={"display_name": "Web Guest", "client_type": "web"},
        headers=ORIGIN,
    )
    assert guest.status_code == 200 and web.cookies.get(PAGE_ACCESS_COOKIE)
    assert (await web.get("/lobby")).status_code == 200
    assert (await web.get("/admin")).headers["location"] == "/admin/login"
    assert (await web.post("/api/v1/auth/logout", headers=ORIGIN)).status_code == 204
    assert web.cookies.get(PAGE_ACCESS_COOKIE) is None
    assert (await web.get("/client/room.html")).status_code == 303


async def test_user_and_admin_html_require_their_own_sessions(
    web: AsyncClient, app: FastAPI
) -> None:
    await sign_in(web)
    for path in ("/admin", "/admin/users", "/admin/rooms", "/admin/settings", "/admin/audit"):
        denied = await web.get(path)
        assert denied.status_code == 303 and denied.headers["location"] == "/admin/login"
    email = f"page-admin-{uuid4().hex}@example.com"
    await create_admin(email, "Page Admin", PASSWORD)
    login = await web.get("/admin/login")
    csrf = re.search(r'name="_csrf" value="([^"]+)"', login.text).group(1)
    signed_in = await web.post(
        "/admin/login", data={"_csrf": csrf, "email": email, "password": PASSWORD}
    )
    assert signed_in.status_code == 303
    for path in ("/admin", "/admin/users", "/admin/rooms", "/admin/settings", "/admin/audit"):
        assert (await web.get(path)).status_code == 200
    # Even a valid admin token cannot be reused as a user-page cookie.
    admin_token = web.cookies.get(ADMIN_ACCESS_COOKIE)
    web.cookies.set(PAGE_ACCESS_COOKIE, admin_token, domain="example.test", path="/")
    assert (await web.get("/lobby")).status_code == 303


async def test_disabled_and_password_required_accounts_are_checked_before_html(
    web: AsyncClient, app: FastAPI
) -> None:
    signed_in = await sign_in(web)
    identity = decode_access_token(
        signed_in["access_token"], app.state.auth_service.secret
    ).identity
    async with app.state.session_factory() as db:
        user = await db.get(User, identity.id)
        user.must_change_password = True
        await db.commit()
    forced = await web.get("/rooms/create")
    assert forced.status_code == 303 and forced.headers["location"] == "/account"
    assert (await web.get("/account")).status_code == 200
    async with app.state.session_factory() as db:
        user = await db.get(User, identity.id)
        user.is_active = False
        await db.commit()
    assert (await web.get("/client/account.html")).status_code == 303


async def test_forged_cookie_and_cross_origin_guest_cannot_unlock_pages(web: AsyncClient) -> None:
    web.cookies.set(PAGE_ACCESS_COOKIE, "forged", domain="example.test", path="/")
    assert (await web.get("/lobby")).status_code == 303
    guest = await web.post(
        "/api/v1/auth/guest",
        json={"display_name": "Guest", "client_type": "web"},
        headers={"Origin": "https://other.test"},
    )
    assert guest.status_code == 403
    assert web.cookies.get(PAGE_ACCESS_COOKIE) is None
