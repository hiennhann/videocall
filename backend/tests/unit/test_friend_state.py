import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.core.errors import AuthError, ErrorCode
from app.models import User
from app.realtime.friends import FriendRealtime
from app.realtime.state import Connection, RoomStateStore
from app.services.friend_events import FriendEvents
from app.services.friend_service import FriendService, canonical_pair
from app.services.settings_service import SettingsService


def test_friend_pair_is_identical_for_both_directions_and_uuid_byte_order() -> None:
    first, second = (
        UUID("12345678-0000-0000-0000-000000000000"),
        UUID("ffffffff-0000-0000-0000-000000000000"),
    )
    assert canonical_pair(first, second) == canonical_pair(second, first)
    low, high = canonical_pair(second, first)
    assert low.bytes < high.bytes


async def test_service_rejects_guest_before_using_database() -> None:
    service = FriendService(SettingsService(), FriendEvents())
    with pytest.raises(AuthError) as exc:
        await service.search(None, None, "user@example.com")
    assert exc.value.code == ErrorCode.GUEST_NOT_ALLOWED


async def test_friend_cache_avoids_repeat_queries_and_is_not_kept_for_offline_users() -> None:
    owner, friend = uuid4(), User(id=uuid4())
    db = SimpleNamespace(execute=AsyncMock(return_value=[(friend, None)]))
    state = RoomStateStore()
    events = FriendRealtime(SimpleNamespace(), state, SettingsService())
    assert await events._ids(db, owner) == {friend.id}
    assert not events._friends
    state.add_connection(Connection("sid", str(owner), "Owner", "user", uuid4(), "test"))
    assert await events._ids(db, owner) == {friend.id}
    assert await events._ids(db, owner) == {friend.id}
    assert db.execute.await_count == 2
    events.invalidate(owner)
    assert await events._ids(db, owner) == {friend.id}
    assert db.execute.await_count == 3


async def test_shutdown_cancels_offline_timers_and_releases_presence_memory() -> None:
    events = FriendRealtime(SimpleNamespace(), RoomStateStore(), SettingsService())
    owner = uuid4()
    events._announced.add(owner)
    events.disconnected(owner)
    tasks = tuple(events._offline.values())
    await events.stop()
    assert tasks and all(task.done() for task in tasks)
    assert not events._friends and not events._offline and not events._announced
    events.disconnected(uuid4())
    await asyncio.sleep(0)
    assert not events._offline
