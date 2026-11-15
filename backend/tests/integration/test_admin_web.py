import asyncio
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.cli import create_admin
from app.core.security import decode_access_token, issue_access_token
from app.web.session import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE

PASSWORD = "test-admin-password"


@pytest_asyncio.fixture
async def web(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://example.test") as client,
    ):
        yield client


def form_token(response: Response) -> str:
    match = re.search(r'name="_csrf" value="([^"]+)"', response.text)
    assert match is not None
    return match[1]


async def sign_in(web: AsyncClient, *, admin: bool = True) -> tuple[str, Response]:
    email = f"a6-{uuid4().hex}@example.com"
    if admin:
        await create_admin(email, "Web Admin", PASSWORD)
    else:
        registered = await web.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "display_name": "Member",
            },
        )
        assert registered.status_code == 201
    login = await web.get("/admin/login")
    response = await web.post(
        "/admin/login", data={"_csrf": form_token(login), "email": email, "password": PASSWORD}
    )
    return email, response


async def test_cookie_scope_roles_csrf_logout_and_login_audit(web: AsyncClient) -> None:
    redirect = await web.get("/admin")
    assert redirect.status_code == 303 and redirect.headers["location"] == "/admin/login"
    rejected = await web.post("/admin/login", data={"email": "x@example.com", "password": PASSWORD})
    assert rejected.status_code == 403
    _, rejected = await sign_in(web, admin=False)
    assert rejected.status_code == 403
    assert web.cookies.get(ACCESS_COOKIE) is None
    email, login = await sign_in(web)
    assert login.status_code == 303 and login.headers["location"] == "/admin"
    for cookie in login.headers.get_list("set-cookie"):
        for flag in ("Path=/admin", "HttpOnly", "Secure", "SameSite=strict"):
            assert flag.lower() in cookie.lower()
    assert (
        web.cookies.get(ACCESS_COOKIE)
        and web.cookies.get(REFRESH_COOKIE)
        and web.cookies.get(CSRF_COOKIE)
    )
    dashboard = await web.get("/admin")
    assert dashboard.status_code == 200 and "Tài khoản mới trong 7 ngày" in dashboard.text
    assert "frame-ancestors 'none'" in dashboard.headers["content-security-policy"]
    assert dashboard.headers["cache-control"] == "no-store"
    audit = await web.get("/admin/audit", params={"actor": email, "action": "admin.login"})
    assert audit.status_code == 200 and "admin.login" in audit.text and email in audit.text
    assert (await web.get("/api/v1/admin/dashboard")).status_code == 401

    stale_refresh = web.cookies.get(REFRESH_COOKIE)
    denied_logout = await web.post("/admin/logout", data={"_csrf": "forged"})
    assert denied_logout.status_code == 403
    logout = await web.post("/admin/logout", data={"_csrf": form_token(dashboard)})
    assert logout.status_code == 303 and logout.headers["location"] == "/admin/login"
    assert web.cookies.get(REFRESH_COOKIE) is None
    refresh = await web.post("/api/v1/auth/refresh", json={"refresh_token": stale_refresh})
    assert refresh.status_code == 401


async def test_middleware_refreshes_and_reuses_the_live_csrf_for_concurrent_requests(
    web: AsyncClient,
    app: FastAPI,
) -> None:
    _, login = await sign_in(web)
    assert login.status_code == 303
    old_refresh = web.cookies.get(REFRESH_COOKIE)
    csrf = web.cookies.get(CSRF_COOKIE)
    secret = app.state.auth_service.secret
    access_token = web.cookies.get(ACCESS_COOKIE)
    assert access_token is not None
    identity = decode_access_token(access_token, secret).identity
    expired, _ = issue_access_token(identity, secret, datetime.now(UTC) - timedelta(hours=1))
    web.cookies.set(ACCESS_COOKIE, expired, domain="example.test", path="/admin")
    users, rooms = await asyncio.gather(web.get("/admin/users"), web.get("/admin/rooms"))
    assert users.status_code == rooms.status_code == 200
    assert web.cookies.get(ACCESS_COOKIE)
    assert web.cookies.get(REFRESH_COOKIE) != old_refresh
    assert web.cookies.get(CSRF_COOKIE) == csrf


async def test_csrf_from_another_admin_session_cannot_authorize_mutations(
    web: AsyncClient, app: FastAPI
) -> None:
    _, login = await sign_in(web)
    assert login.status_code == 303
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://example.test"
    ) as other:
        _, login = await sign_in(other)
        assert login.status_code == 303
        foreign = other.cookies.get(CSRF_COOKIE)
    assert foreign is not None
    web.cookies.set(CSRF_COOKIE, foreign, domain="example.test", path="/admin")
    denied = await web.post(
        "/admin/settings/allow_guest", data={"_csrf": foreign, "value": "false"}
    )
    assert denied.status_code == 403
    assert (await web.get("/api/v1/config/public")).json()["allow_guest"] is True


async def test_admin_html_actions_reuse_room_and_settings_services(web: AsyncClient) -> None:
    _, login = await sign_in(web)
    assert login.status_code == 303
    csrf = form_token(await web.get("/admin/settings"))
    htmx = {"HX-Request": "true"}
    try:
        denied = await web.post("/admin/settings/allow_guest", data={"value": "false"})
        assert denied.status_code == 403
        updated = await web.post(
            "/admin/settings/allow_guest",
            headers=htmx,
            data={
                "_csrf": csrf,
                "operation": "save",
                "value": "false",
            },
        )
        assert updated.headers["hx-redirect"] == "/admin/settings"
        assert (await web.get("/api/v1/config/public")).json()["allow_guest"] is False
    finally:
        await web.post("/admin/settings/allow_guest", data={"_csrf": csrf, "operation": "reset"})
    assert (await web.get("/api/v1/config/public")).json()["allow_guest"] is True

    email = f"a6-room-{uuid4().hex}@example.com"
    account = await web.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "<b>Member</b>",
        },
    )
    assert account.status_code == 201
    user_id = account.json()["id"]
    signed_in = await web.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    auth = {"Authorization": "Bearer " + signed_in.json()["access_token"]}
    user_page = await web.get(f"/admin/users/{user_id}")
    assert "&lt;b&gt;Member&lt;/b&gt;" in user_page.text
    patched = await web.post(
        f"/admin/users/{user_id}", data={"_csrf": csrf, "display_name": "Renamed"}
    )
    assert patched.status_code == 303
    assert "Renamed" in (await web.get(f"/admin/users/{user_id}")).text

    room = await web.post("/api/v1/rooms", headers=auth, json={"name": "Admin Web Room"})
    assert room.status_code == 201
    code = room.json()["code"]
    assert "Admin Web Room" in (await web.get("/admin/rooms")).text
    closed = await web.post(f"/admin/rooms/{code}/close", data={"_csrf": csrf})
    assert closed.status_code == 303
    assert (await web.get(f"/api/v1/rooms/{code}", headers=auth)).json()["status"] == "closed"
    assert code in (await web.get("/admin/audit", params={"action": "room.close"})).text
