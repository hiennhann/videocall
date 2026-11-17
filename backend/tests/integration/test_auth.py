import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select, update

from app.core.security import Identity, issue_access_token
from app.models import RefreshToken, User
from app.schemas.settings import SettingsSchema


@pytest.fixture
def signup() -> dict[str, str]:
    return {
        "email": f"A2-{uuid4().hex}@example.com",
        "password": "test-password-one",
        "display_name": "  An\x00 Nguyễn  ",
    }


@pytest_asyncio.fixture
async def account(client: AsyncClient, signup: dict[str, str]) -> dict[str, str]:
    response = await client.post("auth/register", json=signup)
    assert response.status_code == 201, response.text
    return {"email": signup["email"], "password": signup["password"]}


async def login(client: AsyncClient, account: dict[str, str]) -> dict[str, Any]:
    response = await client.post("auth/login", json=account)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


async def refresh(client: AsyncClient, token: str) -> Response:
    return await client.post("auth/refresh", json={"refresh_token": token})


async def transfer_request(client: AsyncClient, account: dict[str, str]) -> dict[str, str]:
    response = await client.post("auth/login", json=account)
    assert_error(response, 409, "DEVICE_TRANSFER_REQUIRED")
    assert response.headers["cache-control"] == "no-store"
    return {"transfer_token": response.json()["error"]["details"]["transfer_token"]}


async def test_confirm_cancel_and_concurrent_device_transfer(
    client: AsyncClient, account: dict[str, str]
) -> None:
    old = await login(client, account)
    canceled = await transfer_request(client, account)
    assert (await client.post("auth/device-transfer/cancel", json=canceled)).status_code == 204
    assert_error(
        await client.post("auth/device-transfer/confirm", json=canceled),
        409,
        "DEVICE_TRANSFER_INVALID",
    )
    assert (await client.get("me", headers=bearer(old["access_token"]))).status_code == 200

    pending = await transfer_request(client, account)
    results = await asyncio.gather(
        client.post("auth/device-transfer/confirm", json=pending),
        client.post("auth/device-transfer/confirm", json=pending),
    )
    assert sorted(response.status_code for response in results) == [200, 409]
    current = next(response.json() for response in results if response.status_code == 200)
    assert_error(await client.get("me", headers=bearer(old["access_token"])), 401, "TOKEN_INVALID")
    assert_error(await refresh(client, old["refresh_token"]), 401, "INVALID_REFRESH_TOKEN")
    assert (await client.get("me", headers=bearer(current["access_token"]))).status_code == 200


async def test_browser_cookie_session_can_be_shared_across_tabs(
    app: FastAPI, account: dict[str, str]
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test/api/v1/"
    ) as web:
        credentials = {**account, "client_type": "web"}
        origin = {"Origin": "https://test"}
        assert_error(
            await web.post("auth/login", json=credentials, headers={"Origin": "https://other"}),
            403,
            "FORBIDDEN",
        )
        signed_in = await web.post("auth/login", json=credentials, headers=origin)
        assert signed_in.status_code == 200
        assert "refresh_token" not in signed_in.json()
        cookie = signed_in.headers["set-cookie"].lower()
        assert all(
            flag in cookie
            for flag in ("path=/api/v1/auth", "httponly", "secure", "samesite=strict")
        )
        for _ in range(2):
            response = await web.post("auth/refresh", headers=origin)
            assert response.status_code == 200 and "refresh_token" not in response.json()
        assert (await web.post("auth/logout", headers=origin)).status_code == 204
        assert_error(await web.post("auth/refresh", headers=origin), 401, "INVALID_REFRESH_TOKEN")


async def test_register_login_and_update_profile(
    client: AsyncClient, app: FastAPI, signup: dict[str, str]
) -> None:
    registered = await client.post("auth/register", json=signup)
    assert registered.status_code == 201, registered.text
    user = registered.json()
    assert user["email"] == signup["email"].lower()
    assert user["display_name"] == "An Nguyễn"
    assert user["role"] == "user"
    assert "password_hash" not in user
    assert "access_token" not in user

    assert_error(
        await client.post("auth/register", json={**signup, "email": user["email"]}),
        409,
        "EMAIL_TAKEN",
    )
    invalid = await client.post("auth/register", json={**signup, "password": "short"})
    assert_error(invalid, 422, "VALIDATION_ERROR")
    assert "password" in invalid.json()["error"]["details"]["fields"]
    assert "short" not in invalid.text

    tokens = await login(client, {"email": f" {signup['email']} ", "password": signup["password"]})
    assert tokens["expires_in"] == 900
    assert tokens["user"] == {key: user[key] for key in ("id", "email", "display_name", "role")} | {
        "must_change_password": False
    }
    headers = bearer(tokens["access_token"])
    profile = await client.get("me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["is_guest"] is False
    updated = await client.patch("me", headers=headers, json={"display_name": " New Name "})
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "New Name"
    assert (await client.get("me", headers=headers)).json()["display_name"] == "New Name"

    async with app.state.session_factory() as db:
        stored = await db.get(User, UUID(user["id"]))
        token = await db.scalar(select(RefreshToken).where(RefreshToken.user_id == stored.id))
        assert stored.password_hash.startswith("$argon2id$")
        assert signup["password"] not in stored.password_hash
        assert token.token_hash == sha256(tokens["refresh_token"].encode()).hexdigest()


async def test_authentication_errors_and_guest(client: AsyncClient, app: FastAPI) -> None:
    assert_error(await client.get("me"), 401, "UNAUTHENTICATED")
    assert_error(await client.get("me", headers=bearer("invalid")), 401, "TOKEN_INVALID")
    expired, _ = issue_access_token(
        Identity(uuid4(), "Guest"),
        app.state.auth_service.secret,
        datetime.now(UTC) - timedelta(hours=3),
    )
    assert_error(await client.get("me", headers=bearer(expired)), 401, "TOKEN_EXPIRED")
    missing, _ = issue_access_token(
        Identity(uuid4(), "Deleted", uuid4()), app.state.auth_service.secret, datetime.now(UTC)
    )
    assert_error(await client.get("me", headers=bearer(missing)), 401, "TOKEN_INVALID")

    response = await client.post("auth/guest", json={"display_name": " Guest "})
    assert response.status_code == 200
    guest = response.json()
    assert guest["expires_in"] == 7200
    assert guest["user"]["id"].startswith("guest:")
    assert "refresh_token" not in guest
    headers = bearer(guest["access_token"])
    me = await client.get("me", headers=headers)
    assert me.status_code == 200
    assert me.json()["is_guest"] is True
    assert me.json()["email"] is None
    assert "expires_at" in me.json()
    assert_error(
        await client.patch("me", headers=headers, json={"display_name": "Other"}),
        403,
        "GUEST_NOT_ALLOWED",
    )
    assert_error(await client.post("auth/logout-all", headers=headers), 403, "GUEST_NOT_ALLOWED")
    assert_error(
        await client.post(
            "me/password",
            headers=headers,
            json={"current_password": "old", "new_password": "new-pass-123"},
        ),
        403,
        "GUEST_NOT_ALLOWED",
    )


async def test_login_lock_is_per_normalized_email_and_ip(
    client: AsyncClient, app: FastAPI, account: dict[str, str]
) -> None:
    wrong = {**account, "password": "wrong"}
    unknown = await client.post("auth/login", json={**wrong, "email": f"{uuid4().hex}@example.com"})
    for _ in range(4):
        same_user = await client.post("auth/login", json=wrong)
        assert_error(same_user, 401, "INVALID_CREDENTIALS")
        assert same_user.json() == unknown.json()

    locked = await client.post(
        "auth/login", json={**wrong, "email": f" {account['email'].lower()} "}
    )
    assert_error(locked, 429, "LOGIN_LOCKED")
    assert 0 < int(locked.headers["retry-after"]) <= 900
    assert_error(
        await client.post("auth/login", json=account, headers={"X-Forwarded-For": "192.0.2.4"}),
        429,
        "LOGIN_LOCKED",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("192.0.2.1", 80)), base_url=client.base_url
    ) as second_ip:
        await login(second_ip, account)


async def test_refresh_rotation_concurrent_reuse_and_expiry(
    client: AsyncClient, app: FastAPI, account: dict[str, str]
) -> None:
    original = (await login(client, account))["refresh_token"]
    other_account = {**account, "email": f"other-{uuid4().hex}@example.com"}
    registered = await client.post("auth/register", json={**other_account, "display_name": "Other"})
    assert registered.status_code == 201
    other_session = (await login(client, other_account))["refresh_token"]
    responses = await asyncio.gather(refresh(client, original), refresh(client, original))
    assert sorted(response.status_code for response in responses) == [200, 401]
    success = next(response for response in responses if response.status_code == 200)
    replacement = success.json()["refresh_token"]
    assert "user" not in success.json()
    rotating_again = await refresh(client, replacement)
    assert rotating_again.status_code == 200
    latest = rotating_again.json()["refresh_token"]

    async with app.state.session_factory.begin() as db:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == sha256(original.encode()).hexdigest())
            .values(revoked_at=datetime.now(UTC) - timedelta(seconds=11))
        )
    assert_error(await refresh(client, original), 401, "INVALID_REFRESH_TOKEN")
    assert_error(await refresh(client, latest), 401, "INVALID_REFRESH_TOKEN")
    other_replacement = await refresh(client, other_session)
    assert other_replacement.status_code == 200

    async with app.state.session_factory.begin() as db:
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash
                == sha256(other_replacement.json()["refresh_token"].encode()).hexdigest()
            )
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert_error(
        await refresh(client, other_replacement.json()["refresh_token"]),
        401,
        "INVALID_REFRESH_TOKEN",
    )
    assert_error(await refresh(client, "unknown"), 401, "INVALID_REFRESH_TOKEN")


async def test_logout_and_logout_all(client: AsyncClient, account: dict[str, str]) -> None:
    one = await login(client, account)
    successor = (await refresh(client, one["refresh_token"])).json()["refresh_token"]
    for token in ("unknown", one["refresh_token"], one["refresh_token"]):
        response = await client.post("auth/logout", json={"refresh_token": token})
        assert response.status_code == 204 and not response.content
    assert_error(await refresh(client, successor), 401, "INVALID_REFRESH_TOKEN")

    two = await login(client, account)
    active = await refresh(client, two["refresh_token"])
    assert active.status_code == 200
    response = await client.post("auth/logout-all", headers=bearer(two["access_token"]))
    assert response.status_code == 204 and not response.content
    assert_error(
        await refresh(client, active.json()["refresh_token"]), 401, "INVALID_REFRESH_TOKEN"
    )
    assert_error(await client.get("me", headers=bearer(two["access_token"])), 401, "TOKEN_INVALID")


async def test_change_password_preserves_current_family_and_cancels_transfer(
    client: AsyncClient, account: dict[str, str]
) -> None:
    first = await login(client, account)
    pending = await transfer_request(client, account)
    headers = bearer(first["access_token"])
    new_password = "test-password-two"
    for current, new, code in (
        ("wrong", new_password, "WRONG_PASSWORD"),
        (account["password"], account["password"], "PASSWORD_UNCHANGED"),
    ):
        response = await client.post(
            "me/password", headers=headers, json={"current_password": current, "new_password": new}
        )
        assert_error(response, 400, code)
    changed = await client.post(
        "me/password",
        headers=headers,
        json={"current_password": account["password"], "new_password": new_password},
    )
    assert changed.status_code == 204 and not changed.content
    assert (await refresh(client, first["refresh_token"])).status_code == 200
    assert_error(
        await client.post("auth/device-transfer/confirm", json=pending),
        409,
        "DEVICE_TRANSFER_INVALID",
    )
    assert_error(await client.post("auth/login", json=account), 401, "INVALID_CREDENTIALS")
    await transfer_request(client, {**account, "password": new_password})


@pytest.mark.parametrize(
    ("path", "policy", "status", "code"),
    [
        ("register", SettingsSchema(allow_registration=False), 403, "REGISTRATION_DISABLED"),
        ("guest", SettingsSchema(allow_guest=False), 403, "GUEST_DISABLED"),
        ("guest", SettingsSchema(maintenance_mode=True), 503, "MAINTENANCE_MODE"),
    ],
)
async def test_auth_policy(
    client: AsyncClient,
    app: FastAPI,
    signup: dict[str, str],
    path: str,
    policy: SettingsSchema,
    status: int,
    code: str,
) -> None:
    app.state.settings_service._cached = policy
    assert_error(await client.post(f"auth/{path}", json=signup), status, code)


@pytest.mark.parametrize(
    ("path", "limit"), [("register", 5), ("login", 20), ("refresh", 30), ("guest", 10)]
)
async def test_auth_ip_rate_limits(
    client: AsyncClient, app: FastAPI, signup: dict[str, str], path: str, limit: int
) -> None:
    app.state.settings_service._cached = SettingsSchema(allow_registration=False)
    payload = {**signup, "refresh_token": "unknown"}
    for _ in range(limit):
        response = await client.post(f"auth/{path}", json=payload)
        assert response.json().get("error", {}).get("code") != "RATE_LIMITED"
    blocked = await client.post(f"auth/{path}", json=payload)
    assert_error(blocked, 429, "RATE_LIMITED")
    assert int(blocked.headers["retry-after"]) > 0
