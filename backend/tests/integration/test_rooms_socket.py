import asyncio
import socket
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
import socketio
import uvicorn
from fastapi import FastAPI
from httpx import AsyncClient

from app.cli import create_admin
from app.realtime.server import RealtimeServer


@dataclass(slots=True)
class Server:
    url: str
    http: AsyncClient
    realtime: RealtimeServer


@pytest_asyncio.fixture
async def live(app: FastAPI) -> AsyncIterator[Server]:
    realtime = app.state.realtime
    application = socketio.ASGIApp(realtime.sio, other_asgi_app=app)
    server = uvicorn.Server(uvicorn.Config(application, log_level="error", lifespan="on"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                        raise RuntimeError("Uvicorn dừng trước khi sẵn sàng.")
                    await asyncio.sleep(0.02)
            async with AsyncClient(base_url=f"{url}/api/v1/", timeout=5) as http:
                yield Server(url, http, realtime)
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=10)


def bearer(data: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {data['access_token']}"}


async def account(live: Server, *, admin: bool = False) -> dict[str, Any]:
    email = f"room-{uuid4().hex}@example.com"
    password = "room-test-password"
    if admin:
        await create_admin(email, "Administrator", password)
    else:
        response = await live.http.post(
            "auth/register", json={"email": email, "password": password, "display_name": "Member"}
        )
        assert response.status_code == 201, response.text
    response = await live.http.post("auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


async def guest(live: Server) -> dict[str, Any]:
    response = await live.http.post("auth/guest", json={"display_name": "Visitor"})
    assert response.status_code == 200, response.text
    return response.json()


async def room(live: Server, user: dict[str, Any], **body: Any) -> str:
    response = await live.http.post("rooms", headers=bearer(user), json=body)
    assert response.status_code == 201, response.text
    return response.json()["code"]


class Socket:
    def __init__(self) -> None:
        self.client = socketio.AsyncClient(reconnection=False)
        self.events: dict[str, asyncio.Queue[dict[str, Any]]] = defaultdict(asyncio.Queue)
        for event in (
            "connect_error",
            "peer_joined",
            "peer_left",
            "host_changed",
            "offer",
            "answer",
            "ice_candidate",
            "kicked",
            "room_closed",
            "force_disconnect",
        ):
            self.client.on(event, self.events[event].put)

    @property
    def sid(self) -> str:
        sid = self.client.get_sid()
        assert sid is not None
        return sid

    async def call(self, event: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.client.call(event, data, timeout=3)

    async def event(self, name: str, **fields: Any) -> dict[str, Any]:
        async with asyncio.timeout(4):
            while True:
                data = await self.events[name].get()
                if all(data.get(key) == value for key, value in fields.items()):
                    return data


async def peer(live: Server, stack: AsyncExitStack, user: dict[str, Any]) -> Socket:
    connection = Socket()
    stack.push_async_callback(connection.client.shutdown)
    await connection.client.connect(
        live.url, auth={"token": user["access_token"]}, transports=["websocket"], wait_timeout=4
    )
    return connection


def assert_socket_error(ack: dict[str, Any], code: str) -> None:
    assert ack["ok"] is False and ack["error"]["code"] == code, ack


async def test_room_http_limits_and_closed_status(live: Server) -> None:
    owner = await account(live)
    spectator = await guest(live)
    owner_headers = bearer(owner)
    denied = await live.http.post("rooms", headers=bearer(spectator), json={})
    assert denied.status_code == 403
    unsupported = await live.http.post("rooms", headers=owner_headers, json={"mode": "livestream"})
    assert unsupported.status_code == 400
    invalid = await live.http.post("rooms", headers=owner_headers, json={"is_private": True})
    assert invalid.status_code == 422
    oversized = await live.http.post("rooms", headers=owner_headers, json={"max_participants": 5})
    assert oversized.status_code == 422

    codes = [await room(live, owner) for _ in range(3)]
    too_many = await live.http.post("rooms", headers=owner_headers, json={})
    assert too_many.json()["error"]["code"] == "ROOM_LIMIT_REACHED"
    mine = await live.http.get("rooms/mine", headers=owner_headers)
    assert {item["code"] for item in mine.json()} == set(codes)
    assert (await live.http.get("rooms/abc-abcd-abc", headers=owner_headers)).status_code == 404

    visitor = await account(live)
    assert (await live.http.delete(f"rooms/{codes[0]}", headers=bearer(visitor))).status_code == 403
    assert (await live.http.delete(f"rooms/{codes[0]}", headers=owner_headers)).status_code == 204
    found = await live.http.get(f"rooms/{codes[0]}", headers=bearer(spectator))
    assert found.status_code == 200 and found.json()["status"] == "closed"
    assert found.json()["participants"] == 0


async def test_realtime_join_signaling_replacement_and_host_controls(live: Server) -> None:
    owner = await account(live)
    member = await account(live)
    visitor = await guest(live)
    code = await room(live, owner, is_private=True, password="1234", max_participants=2)
    other_code = await room(live, member)
    async with AsyncExitStack() as stack:
        host = await peer(live, stack, owner)
        other = await peer(live, stack, member)
        outsider = await peer(live, stack, visitor)
        assert (await outsider.call("join_room", {"code": other_code}))["ok"]
        assert_socket_error(await outsider.call("join_room", {"code": code}), "ALREADY_IN_ROOM")

        assert_socket_error(
            await other.call("join_room", {"code": code, "password": "wrong"}), "WRONG_PASSWORD"
        )
        result = await other.call("join_room", {"code": code, "password": "1234"})
        assert result["ok"] and result["data"]["you"]["is_host"]
        assert result["data"]["media_policy"]["default_codec"] == "VP8"
        assert (await host.call("join_room", {"code": code, "password": "1234"}))["data"]["you"][
            "is_host"
        ]
        await other.event("host_changed", host_peer_id=host.sid)

        offer = {"type": "offer", "sdp": "v=0\r\n"}
        assert_socket_error(
            await host.call("offer", {"to": outsider.sid, "sdp": offer}), "PEER_NOT_FOUND"
        )
        assert (await host.call("offer", {"to": other.sid, "sdp": offer}))["ok"]
        assert (await other.event("offer", **{"from": host.sid}))["sdp"] == offer
        answer = {"type": "answer", "sdp": "v=0\r\n"}
        assert (await other.call("answer", {"to": host.sid, "sdp": answer}))["ok"]
        assert (await host.event("answer", **{"from": other.sid}))["sdp"] == answer
        candidate = {"candidate": "test", "sdpMid": "0", "sdpMLineIndex": 0}
        assert (await host.call("ice_candidate", {"to": other.sid, "candidate": candidate}))["ok"]
        assert (await other.event("ice_candidate", **{"from": host.sid}))["candidate"] == candidate
        assert_socket_error(await other.call("kick", {"peer_id": host.sid}), "NOT_ROOM_HOST")

        assert (await outsider.call("leave_room"))["ok"]
        assert_socket_error(
            await outsider.call("join_room", {"code": code, "password": "1234"}), "ROOM_FULL"
        )
        replacement = await peer(live, stack, member)
        assert (await replacement.call("join_room", {"code": code, "password": "1234"}))["ok"]
        await other.event("kicked", reason="SESSION_REPLACED")
        await host.event("peer_left", peer_id=other.sid, reason="session_replaced")
        assert (await host.call("kick", {"peer_id": replacement.sid}))["ok"]
        await replacement.event("kicked", reason="KICKED")
        assert_socket_error(
            await replacement.call("join_room", {"code": code, "password": "1234"}), "BANNED"
        )

        assert (await outsider.call("join_room", {"code": code, "password": "1234"}))["ok"]
        assert (await host.call("close_room"))["ok"]
        await outsider.event("room_closed", reason="host")
        assert_socket_error(
            await outsider.call("join_room", {"code": code, "password": "1234"}), "ROOM_CLOSED"
        )


async def test_admin_kick_lock_and_owner_deletion_notify_live_peers(live: Server) -> None:
    admin = await account(live, admin=True)
    owner = await account(live)
    member = await account(live)
    visitor = await guest(live)
    code = await room(live, owner)
    second_code = await room(live, owner)
    auth = bearer(admin)
    async with AsyncExitStack() as stack:
        host = await peer(live, stack, owner)
        guest_socket = await peer(live, stack, visitor)
        member_socket = await peer(live, stack, member)
        for connection in (host, guest_socket, member_socket):
            assert (await connection.call("join_room", {"code": code}))["ok"]
        overview = await live.http.get("admin/dashboard", headers=auth)
        assert overview.json()["online_connections"] == 3
        listed = await live.http.get("admin/rooms", headers=auth)
        assert listed.status_code == 200
        match = next(item for item in listed.json() if item["code"] == code)
        assert len(match["participants"]) == 3

        kicked = await live.http.post(
            f"admin/rooms/{code}/kick", headers=auth, json={"user_id": member["user"]["id"]}
        )
        assert kicked.status_code == 204, kicked.text
        await member_socket.event("kicked", reason="KICKED")
        assert (await member_socket.call("join_room", {"code": second_code}))["ok"]
        locked = await live.http.patch(
            f"admin/users/{member['user']['id']}", headers=auth, json={"is_active": False}
        )
        assert locked.status_code == 200, locked.text
        await member_socket.event("force_disconnect", reason="ACCOUNT_DISABLED")
        second_presence = live.realtime.state.get_room(second_code)
        assert second_presence is not None and not second_presence.peers

        rejected = Socket()
        stack.push_async_callback(rejected.client.shutdown)
        with pytest.raises(socketio.exceptions.ConnectionError):
            await rejected.client.connect(
                live.url,
                auth={"token": member["access_token"]},
                transports=["websocket"],
                wait_timeout=3,
            )
        refusal = await rejected.event("connect_error")
        assert refusal["data"]["code"] == "ACCOUNT_DISABLED"

        deleted = await live.http.delete(f"admin/users/{owner['user']['id']}", headers=auth)
        assert deleted.status_code == 204, deleted.text
        await guest_socket.event("room_closed", reason="owner_deleted")
        await host.event("force_disconnect", reason="SESSIONS_REVOKED")
        closed = await live.http.get(f"rooms/{code}", headers=bearer(visitor))
        assert closed.json()["status"] == "closed"
        audit = await live.http.get(
            "admin/audit-logs",
            headers=auth,
            params={"action": "room.kick", "actor": admin["user"]["id"]},
        )
        assert audit.json()["items"][0]["target_id"] == code


async def test_room_empty_timeout(live: Server) -> None:
    owner = await account(live)
    code = await room(live, owner)
    presence = live.realtime.state.get_room(code)
    assert presence is not None
    presence.empty_since = datetime.now(UTC) - timedelta(seconds=301)
    await live.realtime.rooms.sweep_empty(live.realtime.sessions)
    result = await live.http.get(f"rooms/{code}", headers=bearer(owner))
    assert result.status_code == 200 and result.json()["status"] == "closed"
    assert live.realtime.state.get_room(code) is None


async def test_temporary_host_transfer_and_http_room_close(live: Server) -> None:
    owner = await account(live)
    first_user = await account(live)
    other_user = await account(live)
    admin = await account(live, admin=True)
    code = await room(live, owner)
    async with AsyncExitStack() as stack:
        first = await peer(live, stack, first_user)
        other = await peer(live, stack, other_user)
        assert (await first.call("join_room", {"code": code}))["data"]["you"]["is_host"]
        assert (await other.call("join_room", {"code": code}))["ok"]
        assert (await first.call("transfer_host", {"peer_id": other.sid}))["ok"]
        await first.event("host_changed", host_peer_id=other.sid)
        assert_socket_error(await first.call("close_room"), "NOT_ROOM_HOST")
        closed = await live.http.delete(f"admin/rooms/{code}", headers=bearer(admin))
        assert closed.status_code == 204
        await first.event("room_closed", reason="admin")
        await other.event("room_closed", reason="admin")


async def test_revoked_family_cannot_reconnect_with_an_unexpired_access_token(live: Server) -> None:
    user = await account(live)
    async with AsyncExitStack() as stack:
        old = await peer(live, stack, user)
        logout = await live.http.post("auth/logout-all", headers=bearer(user))
        assert logout.status_code == 204
        await old.event("force_disconnect", reason="SESSIONS_REVOKED")
        rejected = Socket()
        stack.push_async_callback(rejected.client.shutdown)
        with pytest.raises(socketio.exceptions.ConnectionError):
            await rejected.client.connect(
                live.url,
                auth={"token": user["access_token"]},
                transports=["websocket"],
                wait_timeout=3,
            )
        assert (await rejected.event("connect_error"))["data"]["code"] == "TOKEN_INVALID"
