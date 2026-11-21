import asyncio
import json
import socket
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import socketio
import uvicorn
from fastapi import FastAPI
from httpx import AsyncClient, MockTransport, Request, Response
from PIL import Image
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import select, update

from app.cli import create_admin
from app.models import CallParticipant, DirectMessage, Room, RoomInvite
from app.realtime import friends as friend_realtime
from app.realtime.server import RealtimeServer
from app.services import room_service
from app.sfu.control import SfuClient
from app.web.session import CSRF_COOKIE


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
            "friend_request_received",
            "friend_added",
            "friend_removed",
            "friend_profile_changed",
            "presence_changed",
            "call_invite",
            "call_invite_responded",
            "call_invite_cancelled",
            "dm_message",
            "dm_read",
            "dm_typing",
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


async def make_friends(live: Server, first: dict, second: dict) -> None:
    request = await live.http.post(
        "friends/requests", headers=bearer(first), json={"to_user_id": second["user"]["id"]}
    )
    assert request.status_code == 201, request.text
    accepted = await live.http.post(
        f"friends/requests/{request.json()['id']}/accept", headers=bearer(second)
    )
    assert accepted.status_code == 200, accepted.text


async def test_friend_events_reach_all_own_tabs_without_private_fields(
    live: Server, app: FastAPI, tmp_path
) -> None:
    app.state.avatar_service.root = tmp_path
    first, second, outsider = await account(live), await account(live), await account(live)
    async with AsyncExitStack() as stack:
        sender = await peer(live, stack, first)
        recipient = await peer(live, stack, second)
        tab = await peer(live, stack, second)
        other = await peer(live, stack, outsider)
        assert f"user:{second['user']['id']}" in live.realtime.sio.rooms(recipient.sid)
        response = await live.http.post(
            "friends/requests", headers=bearer(first), json={"to_user_id": second["user"]["id"]}
        )
        assert response.status_code == 201
        for connection in (recipient, tab):
            event = await connection.event("friend_request_received")
            assert event["request"]["id"] == response.json()["id"]
            assert set(event["request"]["from"]) == {"id", "display_name", "avatar_url"}
        assert sender.events["friend_request_received"].empty()
        assert other.events["friend_request_received"].empty()
        assert (
            await live.http.post(
                f"friends/requests/{response.json()['id']}/accept", headers=bearer(second)
            )
        ).status_code == 200
        for connection, expected in ((sender, second), (recipient, first), (tab, first)):
            event = await connection.event("friend_added")
            assert event["user"]["id"] == expected["user"]["id"]
        changed = await live.http.patch(
            "me",
            headers=bearer(first),
            json={"display_name": "Current DB Name", "birth_date": "2004-05-20"},
        )
        assert changed.status_code == 200
        for connection in (recipient, tab):
            event = await connection.event("friend_profile_changed")
            assert event == {
                "user_id": first["user"]["id"],
                "display_name": "Current DB Name",
                "avatar_url": None,
            }
        assert other.events["friend_profile_changed"].empty()
        data = BytesIO()
        with Image.new("RGB", (64, 100), "red") as image:
            image.save(data, format="PNG")
        uploaded = await live.http.put(
            "me/avatar",
            headers=bearer(first),
            files={"file": ("test.png", data.getvalue(), "image/png")},
        )
        assert uploaded.status_code == 200
        for connection in (recipient, tab):
            assert (await connection.event("friend_profile_changed"))["avatar_url"].endswith(
                "-64.webp"
            )
        assert (await live.http.delete("me/avatar", headers=bearer(first))).status_code == 204
        for connection in (recipient, tab):
            assert (await connection.event("friend_profile_changed"))["avatar_url"] is None
        removed = await live.http.delete(f"friends/{second['user']['id']}", headers=bearer(first))
        assert removed.status_code == 204
        for connection in (recipient, tab):
            assert await connection.event("friend_removed") == {"user_id": first["user"]["id"]}
        assert sender.events["friend_removed"].empty()


async def test_presence_first_last_socket_and_quick_reconnect_are_debounced(
    live: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(friend_realtime, "OFFLINE_DELAY", 0.15)
    first, second = await account(live), await account(live)
    await make_friends(live, first, second)
    user_id = second["user"]["id"]
    async with AsyncExitStack() as stack:
        observer = await peer(live, stack, first)
        tab1 = await peer(live, stack, second)
        assert await observer.event("presence_changed") == {"user_id": user_id, "online": True}
        tab2 = await peer(live, stack, second)
        await tab1.client.disconnect()
        await asyncio.sleep(0.03)
        assert observer.events["presence_changed"].empty()
        await tab2.client.disconnect()
        await asyncio.sleep(0.02)
        page = (await live.http.get("friends", headers=bearer(first))).json()
        assert page["items"][0]["is_online"] is True  # Trong khoảng chờ offline.
        tab3 = await peer(live, stack, second)
        await asyncio.sleep(0.2)
        assert observer.events["presence_changed"].empty()
        await tab3.client.disconnect()
        assert await observer.event("presence_changed") == {"user_id": user_id, "online": False}
        assert UUID(user_id) not in live.realtime.social._friends
        await peer(live, stack, second)
        assert await observer.event("presence_changed") == {"user_id": user_id, "online": True}


async def test_hidden_online_status_is_cleared_and_not_broadcast_on_disconnect(
    live: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(friend_realtime, "OFFLINE_DELAY", 0.04)
    first, second = await account(live), await account(live)
    await make_friends(live, first, second)
    async with AsyncExitStack() as stack:
        observer = await peer(live, stack, first)
        hidden = await peer(live, stack, second)
        await observer.event("presence_changed", online=True)
        changed = await live.http.patch(
            "me", headers=bearer(second), json={"privacy": {"show_online_status": False}}
        )
        assert changed.status_code == 200
        assert await observer.event("presence_changed") == {
            "user_id": second["user"]["id"],
            "online": None,
        }
        assert (await live.http.get("friends", headers=bearer(first))).json()["items"][0][
            "is_online"
        ] is None
        await hidden.client.disconnect()
        await asyncio.sleep(0.1)
        assert observer.events["presence_changed"].empty()
        await peer(live, stack, second)
        await asyncio.sleep(0.04)
        assert observer.events["presence_changed"].empty()
        await live.http.patch(
            "me", headers=bearer(second), json={"privacy": {"show_online_status": True}}
        )
        assert await observer.event("presence_changed") == {
            "user_id": second["user"]["id"],
            "online": True,
        }


async def test_block_invalidates_presence_cache_silently_without_kicking_room(
    live: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(friend_realtime, "OFFLINE_DELAY", 0.04)
    first, second = await account(live), await account(live)
    await make_friends(live, first, second)
    code = await room(live, first)
    async with AsyncExitStack() as stack:
        observer, blocked = await peer(live, stack, first), await peer(live, stack, second)
        await observer.event("presence_changed", online=True)
        for connection in (observer, blocked):
            assert (await connection.call("join_room", {"code": code}))["ok"]
        assert UUID(second["user"]["id"]) in live.realtime.social._friends
        response = await live.http.post(
            "blocks", headers=bearer(first), json={"user_id": second["user"]["id"]}
        )
        assert response.status_code == 201
        assert len(live.realtime.state.get_room(code).peers) == 2
        assert blocked.events["friend_removed"].empty()
        await live.http.patch("me", headers=bearer(first), json={"display_name": "Blocked Profile"})
        await asyncio.sleep(0.03)
        assert blocked.events["friend_profile_changed"].empty()
        await blocked.client.disconnect()
        await asyncio.sleep(0.1)
        assert observer.events["presence_changed"].empty()


async def test_http_snapshot_recovers_friend_requests_missed_while_offline(live: Server) -> None:
    first, second = await account(live), await account(live)
    async with AsyncExitStack() as stack:
        old = await peer(live, stack, second)
        await old.client.disconnect()
        sent = await live.http.post(
            "friends/requests", headers=bearer(first), json={"to_user_id": second["user"]["id"]}
        )
        assert sent.status_code == 201
        restored = await peer(live, stack, second)
        snapshot = await live.http.get(
            "friends/requests?direction=incoming", headers=bearer(second)
        )
        assert snapshot.status_code == 200
        assert snapshot.json()["items"][0]["id"] == sent.json()["id"]
        assert restored.events["friend_request_received"].empty()  # Không giả lập phát lại event.


async def test_socket_delivery_failure_keeps_committed_request_for_http_resync(
    live: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = await account(live), await account(live)
    async with AsyncExitStack() as stack:
        await peer(live, stack, second)

        async def broken_emit(*args, **kwargs):
            raise OSError("simulated delivery failure")

        monkeypatch.setattr(live.realtime.sio, "emit", broken_emit)
        sent = await live.http.post(
            "friends/requests", headers=bearer(first), json={"to_user_id": second["user"]["id"]}
        )
        assert sent.status_code == 201
        snapshot = (await live.http.get("friends/requests", headers=bearer(second))).json()
        assert snapshot["items"][0]["id"] == sent.json()["id"]


async def test_guests_do_not_join_user_notification_rooms(live: Server) -> None:
    visitor = await guest(live)
    async with AsyncExitStack() as stack:
        connection = await peer(live, stack, visitor)
        assert live.realtime.sio.rooms(connection.sid) == [connection.sid]
        assert not live.realtime.social._friends
        response = await live.http.get("friends", headers=bearer(visitor))
        assert (
            response.status_code == 403 and response.json()["error"]["code"] == "GUEST_NOT_ALLOWED"
        )


async def test_profile_name_is_snapshotted_until_next_room_join(live: Server) -> None:
    owner = await account(live)
    code = await room(live, owner)
    async with AsyncExitStack() as stack:
        host = await peer(live, stack, owner)
        assert (await host.call("join_room", {"code": code}))["ok"]
        changed = await live.http.patch(
            "me", headers=bearer(owner), json={"display_name": "Updated Profile"}
        )
        assert changed.status_code == 200
        # Lặp join trong cùng cuộc gọi vẫn giữ snapshot; JWT vẫn chứa tên cũ.
        assert (await host.call("join_room", {"code": code}))["ok"]
        connection = live.realtime.state.get_connection(host.sid)
        assert connection.display_name == "Member"
        assert (await host.call("leave_room"))["ok"]
        assert (await host.call("join_room", {"code": code}))["ok"]
        assert connection.display_name == "Updated Profile"


async def send_call_invite(live: Server, code: str, owner: dict, target: dict) -> str:
    response = await live.http.post(
        f"rooms/{code}/invites", headers=bearer(owner), json={"user_ids": [target["user"]["id"]]}
    )
    assert response.status_code == 201, response.text
    return response.json()["sent"][0]["invite_id"]


async def test_private_room_invite_is_bound_to_recipient_and_used_once(live: Server) -> None:
    owner, target, outsider = await account(live), await account(live), await account(live)
    await make_friends(live, owner, target)
    code = await room(live, owner, is_private=True, password="required-pass")
    async with AsyncExitStack() as stack:
        host, other = await peer(live, stack, owner), await peer(live, stack, outsider)
        not_joined = await live.http.post(
            f"rooms/{code}/invites",
            headers=bearer(owner),
            json={"user_ids": [target["user"]["id"]]},
        )
        assert not_joined.status_code == 403
        assert (await host.call("join_room", {"code": code, "password": "required-pass"}))["ok"]
        invite_id = await send_call_invite(live, code, owner, target)
        inbox = await live.http.get("invites", headers=bearer(target))
        assert inbox.json()["items"][0]["id"] == invite_id
        assert (await live.http.get("invites", headers=bearer(outsider))).json()["items"] == []
        assert_socket_error(
            await other.call("join_room", {"code": code, "invite_id": invite_id}), "INVITE_INVALID"
        )
        member = await peer(live, stack, target)
        assert (await member.call("join_room", {"code": code, "invite_id": invite_id}))["ok"]
        assert (await host.event("call_invite_responded"))["status"] == "accepted"
        await live.realtime.disconnect(member.sid, live.realtime.sio.reason.TRANSPORT_CLOSE)
        resumed = await peer(live, stack, target)
        assert (await resumed.call("join_room", {"code": code, "invite_id": invite_id}))["ok"]
        assert (await resumed.call("leave_room"))["ok"]
        assert_socket_error(
            await resumed.call("join_room", {"code": code, "invite_id": invite_id}),
            "INVITE_INVALID",
        )


async def test_invite_decline_block_expiry_and_missed_history(live: Server) -> None:
    owner, target = await account(live), await account(live)
    await make_friends(live, owner, target)
    code = await room(live, owner)
    async with AsyncExitStack() as stack:
        host, member = await peer(live, stack, owner), await peer(live, stack, target)
        assert (await host.call("join_room", {"code": code}))["ok"]
        invite_id = await send_call_invite(live, code, owner, target)
        assert (await member.event("call_invite"))["invite"]["id"] == invite_id
        assert (
            await live.http.post(f"invites/{invite_id}/decline", headers=bearer(target))
        ).status_code == 204
        assert (await host.event("call_invite_responded"))["status"] == "declined"
        expired = await send_call_invite(live, code, owner, target)
        async with live.realtime.sessions.begin() as db:
            await db.execute(
                update(RoomInvite)
                .where(RoomInvite.id == UUID(expired))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        assert_socket_error(
            await member.call("join_room", {"code": code, "invite_id": expired}), "INVITE_EXPIRED"
        )
        history = await live.http.get(
            "me/call-history", params={"type": "missed_invite"}, headers=bearer(target)
        )
        assert history.status_code == 200, history.text
        assert history.json()["items"][0]["type"] == "missed_invite"
        assert history.json()["items"][0]["participants_preview"] == []
        assert (
            await live.http.get(f"me/call-history/{code}/chat-export", headers=bearer(target))
        ).status_code == 404
        blocked = await send_call_invite(live, code, owner, target)
        assert (
            await live.http.post(
                "blocks", headers=bearer(target), json={"user_id": owner["user"]["id"]}
            )
        ).status_code == 201
        await member.event("call_invite_cancelled", invite_id=blocked)
        assert_socket_error(
            await member.call("join_room", {"code": code, "invite_id": blocked}), "INVITE_INVALID"
        )
        assert (
            await live.http.delete("me/call-history", headers=bearer(target))
        ).status_code == 204
        assert (await live.http.get("me/call-history", headers=bearer(target))).json()["total"] == 0


async def test_closing_room_preserves_already_missed_invite(live: Server) -> None:
    owner, target = await account(live), await account(live)
    await make_friends(live, owner, target)
    code = await room(live, owner)
    async with AsyncExitStack() as stack:
        host = await peer(live, stack, owner)
        assert (await host.call("join_room", {"code": code}))["ok"]
        invite_id = await send_call_invite(live, code, owner, target)
        async with live.realtime.sessions.begin() as db:
            await db.execute(
                update(RoomInvite)
                .where(RoomInvite.id == UUID(invite_id))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        assert (await host.call("close_room"))["ok"]
    history = await live.http.get(
        "me/call-history", headers=bearer(target), params={"type": "missed_invite"}
    )
    assert history.status_code == 200, history.text
    assert history.json()["items"][0]["room_code"] == code


async def test_participant_history_export_clear_and_admin_summary(live: Server) -> None:
    owner, member, admin = await account(live), await account(live), await account(live, admin=True)
    code = await room(live, owner, name="History test")
    async with AsyncExitStack() as stack:
        host, guest_peer = await peer(live, stack, owner), await peer(live, stack, member)
        for connection in (host, guest_peer):
            assert (await connection.call("join_room", {"code": code}))["ok"]
        assert (await host.call("chat_message", {"text": "History export test"}))["ok"]
        assert (await guest_peer.call("leave_room"))["ok"]
        assert (await guest_peer.call("join_room", {"code": code}))["ok"]
        assert (await host.call("close_room"))["ok"]
        await live.realtime.history.pending.join()
        await live.realtime.chat.pending.join()
        detail = await live.http.get(f"me/call-history/{code}", headers=bearer(member))
        assert detail.status_code == 200, detail.text
        data = detail.json()
        assert (
            data["type"] == "joined" and data["participants_count"] == 2 and data["chat_available"]
        )
        assert [row["leave_reason"] for row in data["participants"]] == [
            "room_closed",
            "left",
            "room_closed",
        ]
        export = await live.http.get(f"me/call-history/{code}/chat-export", headers=bearer(member))
        assert export.status_code == 200, export.text
        assert (
            export.headers["content-type"].startswith("text/plain")
            and "History export test" in export.text
        )
        assert (
            await live.http.get(f"me/call-history/{code}/chat-export", headers=bearer(admin))
        ).status_code == 404
        assert (
            await live.http.get("admin/call-history", headers=bearer(member))
        ).status_code == 403
        listing = await live.http.get(
            "admin/call-history", params={"host": owner["user"]["id"]}, headers=bearer(admin)
        )
        assert listing.status_code == 200, listing.text
        assert listing.json()["items"][0]["room_code"] == code
        dashboard = await live.http.get("admin/dashboard", headers=bearer(admin))
        assert dashboard.status_code == 200, dashboard.text
        assert dashboard.json()["calls_today"] >= 1
        assert (
            await live.http.delete("me/call-history", headers=bearer(member))
        ).status_code == 204
        assert (
            await live.http.get(f"me/call-history/{code}", headers=bearer(member))
        ).status_code == 404
        still = await live.http.get(f"me/call-history/{code}", headers=bearer(owner))
        assert len(still.json()["participants"]) == 3


async def test_recovery_closes_incomplete_participation(live: Server) -> None:
    owner = await account(live)
    code = await room(live, owner)
    async with live.realtime.sessions.begin() as db:
        room_id = await db.scalar(select(Room.id).where(Room.code == code))
        db.add(
            CallParticipant(
                room_id=room_id,
                user_id=UUID(owner["user"]["id"]),
                display_name="Before restart",
                is_guest=False,
                joined_at=datetime.now(UTC) - timedelta(minutes=2),
            )
        )
    await live.realtime.recover_history()
    history = await live.http.get(f"me/call-history/{code}", headers=bearer(owner))
    row = history.json()["participants"][0]
    assert row["leave_reason"] == "server_restart" and row["left_at"] is not None


async def test_admin_removes_avatar_and_records_audit(live: Server, app: FastAPI, tmp_path) -> None:
    app.state.avatar_service.root = tmp_path
    member, admin = await account(live), await account(live, admin=True)
    user_id = member["user"]["id"]
    data = BytesIO()
    with Image.new("RGB", (64, 64), "blue") as image:
        image.save(data, format="PNG")
    uploaded = await live.http.put(
        "me/avatar",
        headers=bearer(member),
        files={"file": ("avatar.png", data.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 200
    route = f"admin/users/{user_id}/avatar"
    assert (await live.http.delete(route, headers=bearer(member))).status_code == 403
    detail = await live.http.get(f"admin/users/{user_id}", headers=bearer(admin))
    assert detail.json()["avatar_url"] == uploaded.json()["avatar_url"]
    assert detail.json()["friends_count"] == detail.json()["calls_count"] == 0
    assert (await live.http.delete(route, headers=bearer(admin))).status_code == 204
    assert (await live.http.get(f"{live.url}{uploaded.json()['avatar_url']}")).status_code == 404
    audit = await live.http.get(
        "admin/audit-logs",
        params={"action": "user.avatar_remove", "actor": admin["user"]["id"]},
        headers=bearer(admin),
    )
    assert audit.json()["items"][0]["target_id"] == user_id


async def test_private_messages_retry_read_delete_and_block(live: Server) -> None:
    first, second, admin = await account(live), await account(live), await account(live, admin=True)
    await make_friends(live, first, second)
    async with AsyncExitStack() as stack:
        sender, sender_tab = await peer(live, stack, first), await peer(live, stack, first)
        recipient = await peer(live, stack, second)
        other = await peer(live, stack, admin)
        body = {
            "to_user_id": second["user"]["id"],
            "text": "  <b>text only</b>  ",
            "client_msg_id": str(uuid4()),
        }
        sent, retry = await asyncio.gather(
            sender.call("dm_send", body), sender_tab.call("dm_send", body)
        )
        assert sent == retry and sent["ok"], sent
        payload = sent["data"]
        assert payload["message"]["text"] == "<b>text only</b>"
        event = await recipient.event("dm_message")
        assert event == payload
        assert sum(tab.events["dm_message"].qsize() for tab in (sender, sender_tab)) == 1
        assert other.events["dm_message"].empty()
        conversation_id, msg_id = payload["conversation_id"], payload["message"]["id"]
        route = f"conversations/{conversation_id}/messages"
        assert (await live.http.get(route, headers=bearer(admin))).status_code == 403
        listing = (await live.http.get("conversations", headers=bearer(second))).json()
        assert listing["items"][0]["unread_count"] == 1
        assert (
            await recipient.call(
                "dm_read", {"conversation_id": conversation_id, "up_to_id": msg_id}
            )
        )["ok"]
        assert (await sender.event("dm_read"))["up_to_id"] == msg_id
        assert (await live.http.get("conversations", headers=bearer(second))).json()["items"][0][
            "unread_count"
        ] == 0
        assert (
            await live.http.delete(f"{route}/{msg_id}", headers=bearer(second))
        ).status_code == 404
        assert (
            await live.http.delete(f"{route}/{msg_id}", headers=bearer(first))
        ).status_code == 204
        assert (await recipient.event("dm_message"))["message"]["text"] is None
        async with live.realtime.sessions() as db:
            row = await db.get(DirectMessage, msg_id)
            assert row.content == "" and row.deleted_at is not None
        assert (
            await live.http.post(
                "blocks", headers=bearer(second), json={"user_id": first["user"]["id"]}
            )
        ).status_code == 201
        assert_socket_error(
            await sender.call("dm_send", {**body, "client_msg_id": str(uuid4())}), "NOT_FRIENDS"
        )
        retained = await live.http.get(route, headers=bearer(second), params={"after": 0})
        assert retained.status_code == 200 and len(retained.json()["items"]) == 1


async def test_dm_retention_removes_expired_messages_and_repairs_preview(live: Server) -> None:
    first, second = await account(live), await account(live)
    await make_friends(live, first, second)
    async with AsyncExitStack() as stack:
        sender = await peer(live, stack, first)
        result = await sender.call(
            "dm_send",
            {
                "to_user_id": second["user"]["id"],
                "text": "Expiring message",
                "client_msg_id": str(uuid4()),
            },
        )
        assert result["ok"], result
        payload = result["data"]
        async with live.realtime.sessions.begin() as db:
            await db.execute(
                update(DirectMessage)
                .where(DirectMessage.id == payload["message"]["id"])
                .values(created_at=datetime.now(UTC) - timedelta(days=2))
            )
        async with live.realtime.sessions() as db:
            settings = live.realtime.dm.settings
            policy = await settings.get(db)
            settings._cached = policy.model_copy(update={"dm_retention_days": 1})
            await live.realtime.dm.prune(db)
        listing = (await live.http.get("conversations", headers=bearer(second))).json()["items"][0]
        assert listing["last_message"] is None and listing["last_message_at"] is None
        assert listing["unread_count"] == 0


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


async def test_admin_branding_and_maintenance_apply_to_new_room_actions(live: Server) -> None:
    admin = await account(live, admin=True)
    host = await account(live)
    newcomer = await guest(live)
    code = await room(live, host)
    patch = {
        "project_name": "Studio V2",
        "brand_color": "#125E88",
        "brand_font": "serif",
        "meeting_enabled": False,
        "maintenance_message": "Đang bảo trì phòng gọi.",
    }
    async with AsyncExitStack() as stack:
        joined = await peer(live, stack, host)
        assert (await joined.call("join_room", {"code": code}))["ok"]
        try:
            changed = await live.http.patch("admin/settings", json=patch, headers=bearer(admin))
            assert changed.status_code == 200
            public = (await live.http.get("config/public")).json()
            assert {key: public[key] for key in patch} == patch
            blocked = await live.http.post("rooms", headers=bearer(host), json={"mode": "meeting"})
            assert (
                blocked.status_code == 503 and blocked.json()["error"]["code"] == "MAINTENANCE_MODE"
            )
            assert (
                await joined.call("media_state", {"audio": False, "video": True, "screen": False})
            )["ok"]
            guest_socket = await peer(live, stack, newcomer)
            assert_socket_error(
                await guest_socket.call("join_room", {"code": code}), "MAINTENANCE_MODE"
            )
        finally:
            restored = await live.http.patch(
                "admin/settings", json=dict.fromkeys(patch), headers=bearer(admin)
            )
            assert restored.status_code == 200
        assert (await guest_socket.call("join_room", {"code": code}))["ok"]


async def test_dashboard_presence_updates_for_rooms_and_unique_accounts(live: Server) -> None:
    admin = await account(live, admin=True)
    member = await account(live)
    visitor = await guest(live)
    code = await room(live, member)
    dashboard_stream = live.url + "/admin/dashboard/events"
    denied = await live.http.get(dashboard_stream, headers=bearer(member))
    assert denied.status_code == 303
    form = await live.http.get(live.url + "/admin/login")
    csrf = form.cookies[CSRF_COOKIE]
    signed_in = await live.http.post(
        live.url + "/admin/login",
        data={"email": admin["user"]["email"], "password": "room-test-password", "_csrf": csrf},
        headers={"Cookie": f"{CSRF_COOKIE}={csrf}"},
    )
    assert signed_in.status_code == 303
    cookie = "; ".join(f"{key}={value}" for key, value in signed_in.cookies.items())

    async def counts(lines: AsyncIterator[str]) -> dict[str, int]:
        async with asyncio.timeout(4):
            async for line in lines:
                if line.startswith("data: "):
                    return json.loads(line[6:])
        raise AssertionError("Dòng cập nhật Dashboard đã đóng.")

    async with (
        live.http.stream("GET", dashboard_stream, headers={"Cookie": cookie}) as stream,
        AsyncExitStack() as stack,
    ):
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        events = stream.aiter_lines()
        assert await counts(events) == {"rooms_with_participants": 0, "online_accounts": 0}
        first = await peer(live, stack, member)
        assert await counts(events) == {"rooms_with_participants": 0, "online_accounts": 1}
        second = await peer(live, stack, member)
        guest_socket = await peer(live, stack, visitor)
        assert (await guest_socket.call("join_room", {"code": code}))["ok"]
        assert await counts(events) == {"rooms_with_participants": 1, "online_accounts": 1}
        assert (await guest_socket.call("leave_room"))["ok"]
        assert await counts(events) == {"rooms_with_participants": 0, "online_accounts": 1}
        await first.client.disconnect()
        await second.client.disconnect()
        assert await counts(events) == {"rooms_with_participants": 0, "online_accounts": 0}
