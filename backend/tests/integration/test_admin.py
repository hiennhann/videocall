import asyncio
from uuid import uuid4

import pytest_asyncio
from httpx import AsyncClient

from app.cli import create_admin


async def token_for(client: AsyncClient, email: str, password: str) -> dict:
    response = await client.post("auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def headers(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def new_member(client: AsyncClient) -> tuple[str, str, dict]:
    email = f"user-{uuid4().hex}@example.com"
    password = "integration-password"
    response = await client.post(
        "auth/register", json={"email": email, "password": password, "display_name": "Member"}
    )
    assert response.status_code == 201, response.text
    return email, password, await token_for(client, email, password)


@pytest_asyncio.fixture
async def admin(client: AsyncClient) -> dict:
    email = f"admin-{uuid4().hex}@example.com"
    await create_admin(email, "Admin", "integration-password")
    return await token_for(client, email, "integration-password")


async def test_admin_settings_affect_auth_and_public_config(
    client: AsyncClient, admin: dict
) -> None:
    auth = headers(admin)
    original = await client.get("admin/settings", headers=auth)
    assert original.status_code == 200, original.text
    assert original.json()["max_participants_per_room"]["min"] == 2
    assert (await client.get("config/public")).json()["allow_guest"] is True

    try:
        invalid = await client.patch(
            "admin/settings", headers=auth, json={"allow_guest": False, "max_rooms_per_user": 99}
        )
        assert invalid.status_code == 422
        assert (await client.get("config/public")).json()["allow_guest"] is True
        unknown = await client.patch(
            "admin/settings", headers=auth, json={"JWT_SECRET": "not-a-setting"}
        )
        assert unknown.json()["error"]["code"] == "UNKNOWN_SETTING"

        updated = await client.patch(
            "admin/settings",
            headers=auth,
            json={"allow_guest": False, "maintenance_message": "Testing"},
        )
        assert updated.status_code == 200, updated.text
        public = (await client.get("config/public")).json()
        assert public["allow_guest"] is False and public["maintenance_message"] == "Testing"
        denied = await client.post("auth/guest", json={"display_name": "Guest"})
        assert denied.json()["error"]["code"] == "GUEST_DISABLED"

        audit = await client.get(
            "admin/audit-logs",
            headers=auth,
            params={"action": "settings.update", "actor": admin["user"]["email"]},
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()["total"] == 1
        assert audit.json()["items"][0]["detail"]["allow_guest"] == {"before": True, "after": False}
    finally:
        reset = await client.patch(
            "admin/settings", headers=auth, json={"allow_guest": None, "maintenance_message": None}
        )
        assert reset.status_code == 200, reset.text
    assert (await client.get("config/public")).json()["allow_guest"] is True


async def test_admin_account_lifecycle_and_live_permissions(
    client: AsyncClient, admin: dict
) -> None:
    email, password, user = await new_member(client)
    auth = headers(admin)
    user_id = user["user"]["id"]
    url = f"admin/users/{user_id}"
    assert (await client.get("admin/users", headers=headers(user))).status_code == 403
    assert (await client.delete(f"admin/users/{admin['user']['id']}", headers=auth)).json()[
        "error"
    ]["code"] == "CANNOT_MODIFY_SELF"
    dashboard = await client.get("admin/dashboard", headers=auth)
    assert dashboard.status_code == 200, dashboard.text
    assert len(dashboard.json()["new_users_per_day"]) == 7

    listing = await client.get(
        "admin/users", headers=auth, params={"q": email, "page_size": 1, "role": "user"}
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    details = await client.get(url, headers=auth)
    assert details.json()["active_sessions"] == 1
    assert details.json()["last_login_at"]

    locked = await client.patch(url, headers=auth, json={"is_active": False})
    assert locked.status_code == 200, locked.text
    assert (await client.get("me", headers=headers(user))).json()["error"][
        "code"
    ] == "ACCOUNT_DISABLED"
    refresh = await client.post("auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert refresh.status_code == 403 and refresh.json()["error"]["code"] == "ACCOUNT_DISABLED"
    assert (await client.get(url, headers=auth)).json()["active_sessions"] == 0
    assert (await client.patch(url, headers=auth, json={"is_active": True})).status_code == 200

    reset = await client.post(f"{url}/reset-password", headers=auth)
    assert reset.status_code == 200 and reset.headers["cache-control"] == "no-store"
    temporary = reset.json()["temporary_password"]
    old_password = await client.post("auth/login", json={"email": email, "password": password})
    assert old_password.json()["error"]["code"] == "INVALID_CREDENTIALS"
    changed_user = await token_for(client, email, temporary)
    assert changed_user["user"]["must_change_password"] is True
    refreshed = await client.post(
        "auth/refresh", json={"refresh_token": changed_user["refresh_token"]}
    )
    assert refreshed.status_code == 200
    changed_user["access_token"] = refreshed.json()["access_token"]
    assert (await client.get("me", headers=headers(changed_user))).status_code == 200
    forbidden = await client.patch(
        "me", headers=headers(changed_user), json={"display_name": "New Name"}
    )
    assert forbidden.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    changed = await client.post(
        "me/password",
        headers=headers(changed_user),
        json={"current_password": temporary, "new_password": "new-password-123"},
    )
    assert changed.status_code == 204, changed.text

    assert (await client.post(f"{url}/revoke-sessions", headers=auth)).status_code == 204
    assert (await client.get(url, headers=auth)).json()["active_sessions"] == 0
    assert (await client.delete(url, headers=auth)).status_code == 204
    assert (await client.get(url, headers=auth)).status_code == 404
    audit = await client.get(
        "admin/audit-logs", headers=auth, params={"actor": admin["user"]["id"]}
    )
    assert temporary not in audit.text
    actions = {entry["action"] for entry in audit.json()["items"]}
    assert {
        "user.lock",
        "user.unlock",
        "user.reset_password",
        "user.revoke_sessions",
        "user.delete",
    } <= actions


async def test_concurrent_admin_demotions_recheck_caller_role(
    client: AsyncClient, admin: dict
) -> None:
    email = f"admin-{uuid4().hex}@example.com"
    await create_admin(email, "Other Admin", "integration-password")
    other = await token_for(client, email, "integration-password")
    first, second = await asyncio.gather(
        client.patch(
            f"admin/users/{other['user']['id']}", headers=headers(admin), json={"role": "user"}
        ),
        client.patch(
            f"admin/users/{admin['user']['id']}", headers=headers(other), json={"role": "user"}
        ),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 403]
