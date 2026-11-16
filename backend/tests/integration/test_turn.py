import base64
import hmac
import os
from time import time
from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient

from app.cli import create_admin
from app.core.security import decode_access_token

STUN = "stun:turn.example.com:3478"
TURN = "turn:turn.example.com:3478?transport=udp"


async def test_turn_credentials_require_authentication_and_are_rate_limited(
    client: AsyncClient, app: FastAPI
) -> None:
    response = await client.get("turn-credentials")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    visitor = await client.post("auth/guest", json={"display_name": "Visitor"})
    assert visitor.status_code == 200, visitor.text
    token = visitor.json()["access_token"]
    identity = decode_access_token(token, app.state.auth_service.secret).identity
    headers = {"Authorization": f"Bearer {token}"}

    before = int(time())
    response = await client.get("turn-credentials", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    expiration, subject = data["username"].split(":")
    assert subject == str(identity.id)
    assert data["urls"] == [STUN, TURN]
    assert data["ttl"] == 14400
    assert before + data["ttl"] <= int(expiration) <= int(time()) + data["ttl"]
    signature = hmac.new(os.environ["TURN_SECRET"].encode(), data["username"].encode(), "sha1")
    assert base64.b64decode(data["credential"]) == signature.digest()

    for _ in range(9):
        assert (await client.get("turn-credentials", headers=headers)).status_code == 200
    limited = await client.get("turn-credentials", headers=headers)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert int(limited.headers["retry-after"]) > 0


async def test_turn_policy_applies_on_the_next_request(client: AsyncClient) -> None:
    email = f"a7-{uuid4().hex}@example.com"
    password = "integration-password"
    await create_admin(email, "TURN admin", password)
    account = await client.post("auth/login", json={"email": email, "password": password})
    guest = await client.post("auth/guest", json={"display_name": "TURN guest"})
    assert account.status_code == guest.status_code == 200
    admin_headers = {"Authorization": f"Bearer {account.json()['access_token']}"}
    guest_headers = {"Authorization": f"Bearer {guest.json()['access_token']}"}

    try:
        updated = await client.patch(
            "admin/settings",
            headers=admin_headers,
            json={"turn_credential_ttl_seconds": 300, "turn_allow_guests": False},
        )
        assert updated.status_code == 200, updated.text
        denied = await client.get("turn-credentials", headers=guest_headers)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "GUEST_NOT_ALLOWED"
        allowed = await client.get("turn-credentials", headers=admin_headers)
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["ttl"] == 300

        disabled = await client.patch(
            "admin/settings", headers=admin_headers, json={"turn_enabled": False}
        )
        assert disabled.status_code == 200, disabled.text
        for headers in (admin_headers, guest_headers):
            response = await client.get("turn-credentials", headers=headers)
            assert response.status_code == 200, response.text
            assert response.json() == {
                "urls": [STUN],
                "username": None,
                "credential": None,
                "ttl": 0,
            }
    finally:
        reset = await client.patch(
            "admin/settings",
            headers=admin_headers,
            json={
                "turn_enabled": None,
                "turn_allow_guests": None,
                "turn_credential_ttl_seconds": None,
            },
        )
        assert reset.status_code == 200, reset.text
