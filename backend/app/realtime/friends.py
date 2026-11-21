import asyncio
import logging
from functools import wraps
from uuid import UUID

import socketio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import FriendRequest, Friendship, RoomInvite, User
from app.realtime.state import RoomStateStore
from app.schemas.friends import FriendItem, PublicUser, RequestItem
from app.services.friend_events import FriendEvents
from app.services.friend_service import blocked_between, canonical_pair, friend_users
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)
OFFLINE_DELAY = 5.0


def best_effort(method):
    @wraps(method)
    async def deliver(*args, **kwargs):
        try:
            return await method(*args, **kwargs)
        except Exception:
            # DB đã commit; lỗi thông báo không làm API báo thất bại hay lộ payload.
            logger.warning("friend_notification_failed", extra={"event": method.__name__})

    return deliver


class FriendRealtime(FriendEvents):
    def __init__(
        self, sio: socketio.AsyncServer, state: RoomStateStore, settings: SettingsService
    ) -> None:
        self.sio, self.state, self.settings = sio, state, settings
        self._friends: dict[UUID, set[UUID]] = {}
        self._announced: set[UUID] = set()
        self._offline: dict[UUID, asyncio.Task] = {}
        self._transitions = asyncio.Lock()
        self._stopping = False

    def start(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions
        self._stopping = False

    async def stop(self) -> None:
        self._stopping = True
        tasks = tuple(self._offline.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._offline.clear()
        self._friends.clear()
        self._announced.clear()

    def is_online(self, user_id: UUID) -> bool:
        return bool(self.state.connections_for(str(user_id))) or user_id in self._announced

    async def _ids(self, db: AsyncSession, user_id: UUID) -> set[UUID]:
        if user_id in self._friends:
            return self._friends[user_id]
        rows = await db.execute(friend_users(user_id))
        ids = {user.id for user, _ in rows}
        if self.is_online(user_id):
            self._friends[user_id] = ids
        return ids

    def invalidate(self, *user_ids: UUID) -> None:
        for user_id in user_ids:
            self._friends.pop(user_id, None)

    def invalidate_all(self) -> None:
        self._friends.clear()

    async def call_invites_cancelled(self, invites: list[RoomInvite]) -> None:
        for invite in invites:
            await self._emit(
                "call_invite_cancelled",
                {
                    "invite_id": str(invite.id),
                    "reason": "expired" if invite.status == "expired" else "unavailable",
                },
                invite.invitee_id,
            )

    @best_effort
    async def _emit(
        self, event: str, payload: dict, user_id: UUID, *, skip: str | None = None
    ) -> None:
        if self.state.connections_for(str(user_id)):
            await self.sio.emit(event, payload, to=f"user:{user_id}", skip_sid=skip)

    @best_effort
    async def _presence(
        self, user_id: UUID, online: bool | None, *, privacy_change: bool = False
    ) -> None:
        async with self.sessions() as db:
            policy = await self.settings.get(db)
            user = await db.get(User, user_id)
            if not policy.friends_enabled or user is None:
                return
            if not privacy_change and not user.show_online_status:
                return
            if online and not user.is_active:
                return
            recipients = await self._ids(db, user_id)
        for recipient in recipients:
            await self._emit(
                "presence_changed", {"user_id": str(user_id), "online": online}, recipient
            )

    async def connected(self, user_id: UUID) -> None:
        async with self._transitions:
            task = self._offline.pop(user_id, None)
            if task:
                task.cancel()
            if (
                self._stopping
                or user_id in self._announced
                or not self.state.connections_for(str(user_id))
            ):
                return
            self._announced.add(user_id)
            await self._presence(user_id, True)

    def disconnected(self, user_id: UUID) -> None:
        if self._stopping or self.state.connections_for(str(user_id)) or user_id in self._offline:
            return
        self._offline[user_id] = asyncio.create_task(self._later_offline(user_id))

    async def _later_offline(self, user_id: UUID) -> None:
        try:
            await asyncio.sleep(OFFLINE_DELAY)
            async with self._transitions:
                if not self.state.connections_for(str(user_id)):
                    self._announced.discard(user_id)
                    await self._presence(user_id, False)
                    self._friends.pop(user_id, None)
        finally:
            if self._offline.get(user_id) is asyncio.current_task():
                self._offline.pop(user_id, None)

    @best_effort
    async def request_received(self, recipient: UUID, request: RequestItem) -> None:
        async with self.sessions() as db:
            policy = await self.settings.get(db)
            current = await db.get(FriendRequest, request.id)
            user = await db.get(User, recipient)
            sender = await db.get(User, request.from_user.id)
            if (
                not policy.friends_enabled
                or current is None
                or current.status != "pending"
                or user is None
                or not user.is_active
                or sender is None
                or not sender.is_active
            ):
                return
            if await db.scalar(select(blocked_between(current.from_user_id, recipient))):
                return
        await self._emit(
            "friend_request_received",
            {"request": request.model_dump(mode="json", by_alias=True)},
            recipient,
        )

    @best_effort
    async def friendship_added(self, first: UUID, second: UUID) -> None:
        self.invalidate(first, second)
        async with self.sessions() as db:
            if not (await self.settings.get(db)).friends_enabled:
                return
            friendship = await db.get(Friendship, canonical_pair(first, second))
            if friendship is None:
                return
            users = [await db.get(User, user_id) for user_id in (first, second)]
            if any(user is None or not user.is_active for user in users):
                return
            for recipient, other in ((first, users[1]), (second, users[0])):
                item = FriendItem(
                    **PublicUser.from_user(other).model_dump(),
                    since=friendship.created_at,
                    is_online=self.is_online(other.id) if other.show_online_status else None,
                )
                await self._emit("friend_added", {"user": item.model_dump(mode="json")}, recipient)

    @best_effort
    async def friendship_removed(self, first: UUID, second: UUID, *, notify: UUID | None) -> None:
        self.invalidate(first, second)
        if notify is not None:
            async with self.sessions() as db:
                if not (await self.settings.get(db)).friends_enabled:
                    return
            other = second if notify == first else first
            await self._emit("friend_removed", {"user_id": str(other)}, notify)

    @best_effort
    async def profile_changed(self, user_id: UUID, *, visibility_changed: bool = False) -> None:
        self.invalidate_all()
        async with self.sessions() as db:
            user = await db.get(User, user_id)
            if (
                user is None
                or not user.is_active
                or not (await self.settings.get(db)).friends_enabled
            ):
                return
            recipients = await self._ids(db, user_id)
            payload = PublicUser.from_user(user).model_dump(mode="json")
            payload["user_id"] = payload.pop("id")
            visibility = user.show_online_status
        for recipient in recipients:
            await self._emit("friend_profile_changed", payload, recipient)
        if visibility_changed:
            await self._presence(
                user_id, self.is_online(user_id) if visibility else None, privacy_change=True
            )
