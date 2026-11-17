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
from httpx import AsyncClient, MockTransport, Request, Response
from prometheus_client.parser import text_string_to_metric_families

from app.cli import create_admin
from app.realtime.server import RealtimeServer
from app.services import room_service
from app.sfu.control import SfuClient


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
            "chat_message",
            "media_state",
            "force_mute",
            "track_published",
            "track_unpublished",
            "live_speaker_changed",
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


async def test_metrics_capture_room_activity_with_bounded_labels(live: Server) -> None:
    async def scrape() -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
        response = await live.http.get(f"{live.url}/metrics")
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/plain")
        assert response.headers.get("x-request-id")
        assert "raw-route-test" not in response.text
        return {
            (sample.name, tuple(sorted(sample.labels.items()))): sample.value
            for family in text_string_to_metric_families(response.text)
            for sample in family.samples
        }

    baseline = await scrape()
    owner = await account(live)
    visitor = await guest(live)
    code = await room(live, owner)
    lookup = await live.http.get(f"rooms/{code}", headers=bearer(owner))
    assert lookup.status_code == 200 and lookup.headers["x-request-id"]
    assert (await live.http.get(f"{live.url}/raw-route-test")).status_code == 404
    async with AsyncExitStack() as stack:
        host = await peer(live, stack, owner)
        other = await peer(live, stack, visitor)
        for socket_client in (host, other):
            assert (await socket_client.call("join_room", {"code": code}))["ok"]
        forbidden = await other.call("kick", {"peer_id": host.sid})
        assert_socket_error(forbidden, "NOT_ROOM_HOST")
        assert forbidden["error"]["request_id"]
        point = await scrape()
        assert point["socket_connections", ()] == 2
        assert point["room_participants", ()] == 2
        assert point["rooms_active", ()] == baseline["rooms_active", ()] + 1
        assert point["rooms_created_total", ()] == 1
        assert point["room_joins_total", ()] == 2
        assert point["socket_events_total", (("event", "join_room"),)] == 2
        assert point["socket_errors_total", (("code", "NOT_ROOM_HOST"),)] == 1
        assert point["join_room_duration_seconds_count", ()] == 2
        assert (
            point[
                "http_requests_total",
                (("method", "GET"), ("route", "/api/v1/rooms/{code}"), ("status", "200")),
            ]
            == 1
        )
        assert (
            point[
                "http_requests_total",
                (("method", "GET"), ("route", "unmatched"), ("status", "404")),
            ]
            == 1
        )
        assert not any(code in value for _, labels in point for _, value in labels)
        assert (await host.call("kick", {"peer_id": other.sid}))["ok"]
        kicked = await scrape()
        assert kicked["room_kicks_total", ()] == 1
        assert kicked["room_participants", ()] == 1


async def test_mesh_capacity_and_rejoin_after_transport_loss(
    live: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 100.0
    monkeypatch.setattr(room_service, "monotonic", lambda: now)
    owner = await account(live)
    entrants = [await guest(live) for _ in range(4)]
    code = await room(live, owner, is_private=True, password="mesh-pass")
    join = {"code": code, "password": "mesh-pass"}
    async with AsyncExitStack() as stack:
        host = await peer(live, stack, owner)
        assert (await host.call("join_room", join))["ok"]
        participants = [await peer(live, stack, token) for token in entrants]
        for count, member in enumerate(participants[:3], 1):
            ack = await member.call("join_room", join)
            assert ack["ok"] and len(ack["data"]["peers"]) == count
            assert ack["data"]["room"]["max_participants"] == 4
        outsider = participants[3]
        assert_socket_error(await outsider.call("join_room", join), "ROOM_FULL")

        disconnected = participants[0]
        old_id = disconnected.sid
        await disconnected.client.eio.ws.close()
        await host.event("peer_left", peer_id=old_id, reason="disconnected")
        assert_socket_error(await outsider.call("join_room", join), "ROOM_FULL")

        returned = await peer(live, stack, entrants[0])
        assert_socket_error(
            await returned.call("join_room", {**join, "password": "bad-password"}),
            "WRONG_PASSWORD",
        )
        joined = await returned.call("join_room", join)
        assert joined["ok"] and len(joined["data"]["peers"]) == 3
        assert_socket_error(await outsider.call("join_room", join), "ROOM_FULL")

        old_id = returned.sid
        await returned.client.eio.ws.close()
        await host.event("peer_left", peer_id=old_id, reason="disconnected")
        now += 10
        assert (await outsider.call("join_room", join))["ok"]
        assert (await outsider.call("leave_room"))["ok"]
        returned = await peer(live, stack, entrants[0])
        assert (await returned.call("join_room", join))["ok"]


async def test_livestream_enforces_speaker_permissions_and_capacity(live: Server) -> None:
    requests: list[tuple[str, str]] = []

    def control(request: Request) -> Response:
        requests.append((request.method, request.url.path))
        if request.method == "PUT":
            return Response(200, json={"type": "answer", "sdp": "v=0\r\n"})
        return Response(204)

    sfu = SfuClient("http://sfu", "test-control-secret")
    await sfu.http.aclose()
    sfu.http = AsyncClient(base_url="http://sfu", transport=MockTransport(control))
    live.realtime.rooms.sfu = sfu
    owner = await account(live)
    entrants = [await guest(live) for _ in range(5)]
    code = await room(live, owner, mode="livestream")
    description = {"type": "offer", "sdp": "v=0\r\n"}
    publish = {"to": "sfu", "sdp": description}
    async with AsyncExitStack() as stack:
        host = await peer(live, stack, owner)
        viewers = [await peer(live, stack, token) for token in entrants]
        joined = await host.call("join_room", {"code": code})
        assert joined["data"]["room"]["speaker_peer_id"] == host.sid
        assert joined["data"]["room"]["max_participants"] == 5
        for viewer in viewers[:4]:
            assert (await viewer.call("join_room", {"code": code}))["ok"]
        assert_socket_error(await viewers[4].call("join_room", {"code": code}), "ROOM_FULL")

        viewer = viewers[0]
        assert_socket_error(await viewer.call("offer", publish), "NOT_LIVE_SPEAKER")
        assert_socket_error(await viewer.call("subscribe", description), "STREAM_NOT_READY")
        assert_socket_error(
            await viewer.call("promote_speaker", {"peer_id": viewer.sid}), "NOT_ROOM_HOST"
        )
        assert requests == []
        assert (await host.call("offer", publish))["data"]["type"] == "answer"
        await viewer.event("track_published", peer_id=host.sid)
        assert (await viewer.call("subscribe", description))["ok"]
        assert (await host.call("promote_speaker", {"peer_id": viewer.sid}))["ok"]
        await viewer.event("track_unpublished", peer_id=host.sid)
        await viewer.event("live_speaker_changed", speaker_peer_id=viewer.sid)
        assert_socket_error(await host.call("offer", publish), "NOT_LIVE_SPEAKER")
        assert (await viewer.call("offer", publish))["ok"]
        await host.event("track_published", peer_id=viewer.sid)
        assert (await host.call("subscribe", description))["ok"]
        assert (await host.call("demote_speaker"))["ok"]
        await host.event("track_unpublished", peer_id=viewer.sid)
        assert_socket_error(await viewer.call("offer", publish), "NOT_LIVE_SPEAKER")
        assert (await host.call("close_room"))["ok"]
        assert requests.count(("DELETE", f"/rooms/{code}")) == 3


async def test_chat_broadcast_history_cursor_and_membership(live: Server) -> None:
    owner = await account(live)
    visitor = await guest(live)
    outsider = await guest(live)
    code = await room(live, owner, is_private=True, password="private-chat")
    another = await room(live, owner)
    path = f"rooms/{code}/messages"
    assert (await live.http.get(path)).status_code == 401
    empty = await live.http.get(path, headers=bearer(owner))
    assert empty.status_code == 200 and empty.json() == {"items": [], "next_before": None}
    denied = await live.http.get(path, headers=bearer(visitor))
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "NOT_IN_ROOM"

    async with AsyncExitStack() as stack:
        host = await peer(live, stack, owner)
        sender = await peer(live, stack, visitor)
        other_room = await peer(live, stack, outsider)
        assert (await host.call("join_room", {"code": code, "password": "private-chat"}))["ok"]
        assert (await sender.call("join_room", {"code": code, "password": "private-chat"}))["ok"]
        assert (await other_room.call("join_room", {"code": another}))["ok"]
        assert_socket_error(await sender.call("chat_message", {"text": " "}), "INVALID_PAYLOAD")
        assert_socket_error(
            await sender.call("chat_message", {"text": "a" * 2001}), "INVALID_PAYLOAD"
        )
        text = "<b>literal message</b>"
        sent = await sender.call("chat_message", {"text": f"  {text} "})
        assert sent["ok"], sent
        first = await sender.event("chat_message", text=text)
        assert await host.event("chat_message", text=text) == first
        assert first["id"] == sent["data"]["id"]
        assert first["from"] == {"peer_id": sender.sid, "user_id": None, "display_name": "Visitor"}
        assert other_room.events["chat_message"].empty()

        sent = await host.call("chat_message", {"text": "second"})
        assert sent["ok"], sent
        newest = await sender.event("chat_message", text="second")
        await asyncio.wait_for(live.realtime.chat.pending.join(), timeout=4)
        result = await live.http.get(path, headers=bearer(visitor), params={"limit": 1})
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "no-store"
        latest = result.json()
        assert latest["items"][0]["id"] == latest["next_before"] == newest["id"]
        assert latest["items"][0]["content"] == "second"
        assert latest["items"][0]["user_id"] == owner["user"]["id"]
        earlier = await live.http.get(
            path, headers=bearer(visitor), params={"limit": 1, "before": latest["next_before"]}
        )
        assert earlier.status_code == 200, earlier.text
        item = earlier.json()["items"][0]
        assert (item["id"], item["user_id"], item["content"]) == (first["id"], None, text)
        assert earlier.json()["next_before"] is None
        assert (
            await live.http.get(path, headers=bearer(owner), params={"limit": 101})
        ).status_code == 422
        assert (await sender.call("leave_room"))["ok"]
        assert_socket_error(await sender.call("chat_message", {"text": "outside"}), "NOT_IN_ROOM")
        assert (await live.http.get(path, headers=bearer(visitor))).status_code == 403
        assert (await host.call("leave_room"))["ok"]
        owner_history = await live.http.get(path, headers=bearer(owner))
        assert [item["id"] for item in owner_history.json()["items"]] == [newest["id"], first["id"]]


async def test_a8_live_policies_rate_limit_and_host_mute(live: Server) -> None:
    owner = await account(live, admin=True)
    visitor = await guest(live)
    code = await room(live, owner)
    auth = bearer(owner)
    active_screen = {"audio": False, "video": True, "screen": True, "screen_stream_id": "display-1"}
    try:
        async with AsyncExitStack() as stack:
            host = await peer(live, stack, owner)
            guest_socket = await peer(live, stack, visitor)
            assert (await host.call("join_room", {"code": code}))["ok"]
            assert (await guest_socket.call("join_room", {"code": code}))["ok"]
            assert_socket_error(
                await guest_socket.call("mute_peer", {"peer_id": host.sid, "kind": "audio"}),
                "NOT_ROOM_HOST",
            )
            assert_socket_error(
                await host.call("mute_peer", {"peer_id": "other-room", "kind": "audio"}),
                "PEER_NOT_FOUND",
            )
            for kind in ("audio", "video"):
                assert (await host.call("mute_peer", {"peer_id": guest_socket.sid, "kind": kind}))[
                    "ok"
                ]
                assert await guest_socket.event("force_mute", kind=kind) == {
                    "kind": kind,
                    "by_peer_id": host.sid,
                }
            assert host.events["force_mute"].empty()

            assert_socket_error(
                await host.call("media_state", {**active_screen, "screen_stream_id": None}),
                "INVALID_PAYLOAD",
            )
            assert (await host.call("media_state", active_screen))["ok"]
            assert await guest_socket.event("media_state", peer_id=host.sid) == {
                "peer_id": host.sid,
                **active_screen,
            }
            rejoined = await guest_socket.call("join_room", {"code": code})
            assert rejoined["data"]["peers"][0]["media"] == active_screen
            assert host.events["media_state"].empty()

            updated = await live.http.patch(
                "admin/settings",
                headers=auth,
                json={"chat_history_enabled": False, "allow_screen_share": False},
            )
            assert updated.status_code == 200, updated.text
            assert_socket_error(
                await guest_socket.call("media_state", active_screen), "SCREEN_SHARE_DISABLED"
            )
            assert (await host.call("media_state", {**active_screen, "video": False}))["ok"]
            stopped = {**active_screen, "screen": False, "screen_stream_id": None}
            assert (await host.call("media_state", stopped))["ok"]

            for i in range(5):
                assert (await guest_socket.call("chat_message", {"text": f"message {i}"}))["ok"]
            assert_socket_error(
                await guest_socket.call("chat_message", {"text": "sixth"}), "RATE_LIMITED"
            )
            assert (await host.event("chat_message", text="message 4"))["text"] == "message 4"
            history = await live.http.get(f"rooms/{code}/messages", headers=auth)
            assert history.json() == {"items": [], "next_before": None}

            updated = await live.http.patch(
                "admin/settings",
                headers=auth,
                json={"chat_enabled": False, "chat_history_enabled": None},
            )
            assert updated.status_code == 200, updated.text
            assert_socket_error(
                await host.call("chat_message", {"text": "disabled"}), "CHAT_DISABLED"
            )
            history = await live.http.get(f"rooms/{code}/messages", headers=auth)
            assert history.json() == {"items": [], "next_before": None}
    finally:
        reset = await live.http.patch(
            "admin/settings",
            headers=auth,
            json={"chat_enabled": None, "chat_history_enabled": None, "allow_screen_share": None},
        )
        assert reset.status_code == 200, reset.text


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


async def test_device_transfer_notifies_and_removes_old_room_peer(live: Server) -> None:
    first = await account(live)
    visitor = await guest(live)
    code = await room(live, first)
    async with AsyncExitStack() as stack:
        old = await peer(live, stack, first)
        witness = await peer(live, stack, visitor)
        assert (await old.call("join_room", {"code": code}))["ok"]
        assert (await witness.call("join_room", {"code": code}))["ok"]
        request = await live.http.post(
            "auth/login", json={"email": first["user"]["email"], "password": "room-test-password"}
        )
        assert request.status_code == 409
        old_peer = old.sid
        confirmed = await live.http.post(
            "auth/device-transfer/confirm",
            json={"transfer_token": request.json()["error"]["details"]["transfer_token"]},
        )
        assert confirmed.status_code == 200
        await old.event("force_disconnect", reason="DEVICE_SESSION_REPLACED")
        await witness.event("peer_left", peer_id=old_peer)
        second = await peer(live, stack, confirmed.json())
        assert (await second.call("join_room", {"code": code}))["ok"]
