import secrets
from datetime import UTC, datetime, timedelta
from string import ascii_lowercase
from time import monotonic
from typing import Any, Literal, Protocol
from uuid import UUID

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AuthError, ErrorCode
from app.core.security import hash_password, verify_password
from app.metrics import Metrics
from app.models import Room, User
from app.realtime.state import Connection, HeldSeat, Peer, RoomPresence, RoomStateStore
from app.schemas.rooms import CreateRoom, MediaState, RoomCreated, RoomSummary, SessionDescription
from app.schemas.settings import SettingsSchema
from app.services.audit_service import AuditActor, record_audit
from app.services.auth_service import AuthService
from app.services.settings_service import SettingsService
from app.sfu.control import Mode, SfuClient

PASSWORD_FAILURES = parse("5/5 minute")
ICE_LIMIT = parse("200/10 second")
MESH_ROOM_LIMIT = 4
LIVE_ROOM_LIMIT = 5
LIVE_OFFERS = parse("8/minute")
REJOIN_GRACE_SECONDS = 10
CODE_LETTERS = ascii_lowercase.translate(str.maketrans("", "", "ilo"))


class RoomEvents(Protocol):
    async def emit(
        self, event: str, payload: dict[str, Any], *, to: str, skip: str | None = None
    ) -> None: ...

    async def enter(self, peer_id: str, code: str) -> None: ...

    async def leave(self, peer_id: str, code: str) -> None: ...


def capacity_for_mode(mode: str, settings: SettingsSchema) -> int:
    if mode == "livestream":
        return LIVE_ROOM_LIMIT
    return min(settings.max_participants_per_room, MESH_ROOM_LIMIT)


def capacity(room: Room, settings: SettingsSchema) -> int:
    maximum = capacity_for_mode(room.mode, settings)
    return min(room.max_participants or maximum, maximum)


def room_result(room: Room, settings: SettingsSchema) -> RoomCreated:
    return RoomCreated(
        code=room.code,
        name=room.name,
        mode=room.mode,
        is_private=room.is_private,
        max_participants=capacity(room, settings),
        host_id=room.host_id,
        status=room.status,
        created_at=room.created_at,
    )


async def find_room(db: AsyncSession, code: str, *, locked: bool = False) -> Room:
    query = select(Room).where(Room.code == code)
    if locked:
        query = query.with_for_update().execution_options(populate_existing=True)
    room = await db.scalar(query)
    if room is None:
        raise AuthError(ErrorCode.ROOM_NOT_FOUND)
    return room


class RoomService:
    def __init__(
        self,
        settings: SettingsService,
        state: RoomStateStore,
        events: RoomEvents,
        metrics: Metrics,
        sfu: SfuClient | None = None,
    ) -> None:
        self.settings = settings
        self.state = state
        self.events = events
        self.metrics = metrics
        self.sfu = sfu
        self.limiter = FixedWindowRateLimiter(MemoryStorage())

    async def create(self, db: AsyncSession, owner_id: UUID, body: CreateRoom) -> RoomCreated:
        settings = await self.settings.get(db)
        if settings.maintenance_mode:
            raise AuthError(ErrorCode.MAINTENANCE_MODE)
        if body.mode == "livestream" and self.sfu is None:
            raise AuthError(ErrorCode.MODE_NOT_SUPPORTED)
        if body.max_participants is not None and body.max_participants > capacity_for_mode(
            body.mode, settings
        ):
            raise AuthError(
                ErrorCode.VALIDATION_ERROR,
                fields={"max_participants": "Vượt giới hạn cấu hình phòng."},
            )
        password_hash = (
            await hash_password(body.password.get_secret_value()) if body.password else None
        )
        owner = await AuthService.lock_user(db, owner_id)
        if owner is None or not owner.is_active:
            raise AuthError(ErrorCode.ACCOUNT_DISABLED)
        if owner.must_change_password:
            raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)

        count = await db.scalar(
            select(func.count())
            .select_from(Room)
            .where(Room.host_id == owner_id, Room.status == "active")
        )
        if count is not None and count >= settings.max_rooms_per_user:
            raise AuthError(ErrorCode.ROOM_LIMIT_REACHED)

        for _ in range(5):
            code = "-".join(
                "".join(secrets.choice(CODE_LETTERS) for _ in range(n)) for n in (3, 4, 3)
            )
            statement = (
                insert(Room)
                .values(
                    code=code,
                    name=body.name,
                    host_id=owner_id,
                    mode=body.mode,
                    is_private=body.is_private,
                    password_hash=password_hash,
                    max_participants=body.max_participants,
                )
                .on_conflict_do_nothing(index_elements=[Room.code])
                .returning(Room)
            )
            room = await db.scalar(statement)
            if room is not None:
                await db.commit()
                self.state.ensure_room(room.code, room.host_id, room.created_at, room.mode)
                self.metrics.rooms_created.inc()
                return room_result(room, settings)
        raise RuntimeError("Không thể tạo mã phòng duy nhất.")

    async def detail(self, db: AsyncSession, code: str) -> RoomSummary:
        settings = await self.settings.get(db)
        room = await find_room(db, code)
        presence = self.state.get_room(code)
        return RoomSummary(
            code=code,
            name=room.name,
            mode=room.mode,
            has_password=room.is_private,
            status=room.status,
            participants=len(presence.peers) if presence and room.status == "active" else 0,
            max_participants=capacity(room, settings),
        )

    async def mine(self, db: AsyncSession, user_id: UUID) -> list[RoomCreated]:
        settings = await self.settings.get(db)
        rows = await db.scalars(
            select(Room)
            .where(Room.host_id == user_id, Room.status == "active")
            .order_by(Room.created_at.desc(), Room.code)
        )
        return [room_result(room, settings) for room in rows]

    async def join(
        self, db: AsyncSession, connection: Connection, code: str, password: str | None
    ) -> dict[str, Any]:
        settings = await self.settings.get(db)
        room = await find_room(db, code)
        if room.status != "active":
            raise AuthError(ErrorCode.ROOM_CLOSED)
        if room.mode == "livestream" and self.sfu is None:
            raise AuthError(ErrorCode.MODE_NOT_SUPPORTED)
        if connection.room_code is not None and connection.room_code != code:
            raise AuthError(ErrorCode.ALREADY_IN_ROOM)
        presence = self.state.ensure_room(code, room.host_id, datetime.now(UTC), room.mode)

        async with presence.lock:
            # Một thao tác đóng phòng có thể đã hoàn tất trong lúc chờ khóa.
            room = await find_room(db, code, locked=True)
            if room.status != "active":
                raise AuthError(ErrorCode.ROOM_CLOSED)
            if connection.user_id in presence.banned:
                raise AuthError(ErrorCode.BANNED)
            if connection.peer_id in presence.peers:
                return self._join_result(
                    room, presence, presence.peers[connection.peer_id], settings
                )

            if room.password_hash is not None:
                key = (connection.user_id, connection.ip)
                if not self.limiter.test(PASSWORD_FAILURES, *key):
                    raise AuthError(ErrorCode.RATE_LIMITED)
                if password is None or not await verify_password(password, room.password_hash):
                    self.limiter.hit(PASSWORD_FAILURES, *key)
                    raise AuthError(ErrorCode.WRONG_PASSWORD)

            previous = next(
                (peer for peer in presence.peers.values() if peer.user_id == connection.user_id),
                None,
            )
            presence.expire_seats(monotonic())
            held = presence.held_seats.get(connection.user_id)
            occupied = len(presence.peers) + len(presence.held_seats)
            if previous is None and held is None and occupied >= capacity(room, settings):
                raise AuthError(ErrorCode.ROOM_FULL)

            old_host = presence.host_id()
            if previous is not None:
                await self.events.emit("kicked", {"reason": "SESSION_REPLACED"}, to=previous.id)
                await self.remove(presence, previous, "session_replaced")
            presence.held_seats.pop(connection.user_id, None)
            prior = previous or held
            peer = Peer(connection, prior.joined_at if prior else datetime.now(UTC))
            self.state.add_peer(presence, peer)
            if presence.owner_id == peer.user_id:
                presence.preferred_host = None
            await self.events.enter(peer.id, code)
            await self.events.emit("peer_joined", {"peer": peer.public()}, to=code, skip=peer.id)
            await self.host_changed(presence, old_host)
            self.metrics.room_joins.inc()
            return self._join_result(room, presence, peer, settings)

    @staticmethod
    def _join_result(
        room: Room, presence: RoomPresence, peer: Peer, settings: SettingsSchema
    ) -> dict[str, Any]:
        host = presence.host_id()
        return {
            "room": {
                "code": room.code,
                "name": room.name,
                "mode": room.mode,
                "max_participants": capacity(room, settings),
                "host_peer_id": host,
                "speaker_peer_id": presence.live_speaker() if room.mode == "livestream" else None,
                "publisher_peer_id": presence.published_by,
            },
            "you": {
                "peer_id": peer.id,
                "user_id": peer.user_id,
                "display_name": peer.connection.display_name,
                "is_host": host == peer.id,
            },
            "peers": [other.public() for other in presence.peers.values() if other.id != peer.id],
            "media_policy": {
                key: getattr(settings, key)
                for key in (
                    "max_video_bitrate_kbps",
                    "max_screen_bitrate_kbps",
                    "max_video_resolution",
                    "default_codec",
                )
            },
            "features": {
                "chat": settings.chat_enabled,
                "screen_share": settings.allow_screen_share and room.mode == "meeting",
            },
        }

    def joined_room(self, connection: Connection) -> RoomPresence:
        presence = self.state.get_room(connection.room_code or "")
        if presence is None or connection.peer_id not in presence.peers:
            raise AuthError(ErrorCode.NOT_IN_ROOM)
        return presence

    async def host_changed(self, presence: RoomPresence, previous: str | None) -> None:
        host = presence.host_id()
        if host != previous and presence.peers:
            await self.events.emit("host_changed", {"host_peer_id": host}, to=presence.code)
            if presence.mode == "livestream":
                await self.sync_speaker(presence)

    async def remove(self, presence: RoomPresence, peer: Peer, reason: str) -> None:
        old_host = presence.host_id()
        speaker_left = presence.speaker_id == peer.id
        if presence.mode == "livestream" and self.sfu is not None:
            if presence.published_by == peer.id:
                await self.stop_publisher(presence)
            else:
                await self.sfu.remove(presence.code, peer.id)
            if speaker_left:
                presence.speaker_id = None
        self.state.remove_peer(presence, peer)
        if presence.preferred_host == peer.user_id and reason != "session_replaced":
            presence.preferred_host = None
        await self.events.leave(peer.id, presence.code)
        await self.events.emit(
            "peer_left", {"peer_id": peer.id, "reason": reason}, to=presence.code
        )
        if speaker_left and presence.host_id() == old_host:
            await self.sync_speaker(presence)

    async def leave(
        self, connection: Connection, reason: str = "left", *, reserve: bool = False
    ) -> None:
        presence = self.state.get_room(connection.room_code or "")
        if presence is not None:
            async with presence.lock:
                peer = presence.peers.get(connection.peer_id)
                if peer is not None:
                    host = presence.host_id()
                    if reserve:
                        now = monotonic()
                        presence.expire_seats(now)
                        presence.held_seats[connection.user_id] = HeldSeat(
                            peer.joined_at, now + REJOIN_GRACE_SECONDS
                        )
                    await self.remove(presence, peer, reason)
                    await self.host_changed(presence, host)

    async def signal(
        self, connection: Connection, target: str, event: str, payload: dict[str, Any]
    ) -> None:
        presence = self.joined_room(connection)
        async with presence.lock:
            self.joined_room(connection)
            if presence.mode == "livestream":
                raise AuthError(ErrorCode.INVALID_PAYLOAD)
            if target == connection.peer_id or target not in presence.peers:
                raise AuthError(ErrorCode.PEER_NOT_FOUND)
            if event == "ice_candidate" and not self.limiter.hit(ICE_LIMIT, connection.peer_id):
                raise AuthError(ErrorCode.RATE_LIMITED)
            await self.events.emit(event, {"from": connection.peer_id, **payload}, to=target)

    async def transfer_host(self, connection: Connection, target: str) -> None:
        presence = self.joined_room(connection)
        async with presence.lock:
            self.joined_room(connection)
            old_host = presence.host_id()
            if old_host != connection.peer_id:
                raise AuthError(ErrorCode.NOT_ROOM_HOST)
            peer = presence.peers.get(target)
            if peer is None or peer.connection.is_guest:
                raise AuthError(ErrorCode.PEER_NOT_FOUND)
            presence.preferred_host = peer.user_id
            await self.host_changed(presence, old_host)

    async def stop_publisher(self, presence: RoomPresence) -> None:
        assert self.sfu is not None
        publisher = presence.published_by
        if publisher is not None:
            presence.published_by = None
            await self.sfu.remove(presence.code)
            await self.events.emit("track_unpublished", {"peer_id": publisher}, to=presence.code)

    async def sync_speaker(self, presence: RoomPresence) -> None:
        speaker = presence.live_speaker()
        if presence.published_by is not None and presence.published_by != speaker:
            await self.stop_publisher(presence)
        await self.events.emit(
            "live_speaker_changed", {"speaker_peer_id": speaker}, to=presence.code
        )

    def live_room(self, connection: Connection) -> RoomPresence:
        presence = self.joined_room(connection)
        if presence.mode != "livestream" or self.sfu is None:
            raise AuthError(ErrorCode.MODE_NOT_SUPPORTED)
        return presence

    async def select_speaker(self, connection: Connection, target: str | None) -> None:
        presence = self.live_room(connection)
        async with presence.lock:
            self.joined_room(connection)
            if presence.host_id() != connection.peer_id:
                raise AuthError(ErrorCode.NOT_ROOM_HOST)
            if target is not None and target not in presence.peers:
                raise AuthError(ErrorCode.PEER_NOT_FOUND)
            presence.speaker_id = target
            await self.sync_speaker(presence)

    async def live_offer(
        self, connection: Connection, mode: Mode, sdp: SessionDescription
    ) -> SessionDescription:
        presence = self.live_room(connection)
        async with presence.lock:
            self.joined_room(connection)
            if mode == "publish" and presence.live_speaker() != connection.peer_id:
                raise AuthError(ErrorCode.NOT_LIVE_SPEAKER)
            if mode == "view" and (
                presence.published_by is None or presence.published_by == connection.peer_id
            ):
                raise AuthError(ErrorCode.STREAM_NOT_READY)
            if not self.limiter.hit(LIVE_OFFERS, "livestream", connection.peer_id):
                raise AuthError(ErrorCode.RATE_LIMITED)
            assert self.sfu is not None
            if mode == "publish":
                await self.stop_publisher(presence)
            try:
                answer = await self.sfu.offer(presence.code, connection.peer_id, mode, sdp)
            except AuthError as error:
                if error.code == ErrorCode.STREAM_NOT_READY:
                    await self.stop_publisher(presence)
                raise
            if mode == "publish":
                presence.published_by = connection.peer_id
                await self.events.emit(
                    "track_published",
                    {"peer_id": connection.peer_id, "tracks": ["audio", "video"]},
                    to=presence.code,
                )
            return answer

    async def leave_stream(self, connection: Connection) -> None:
        presence = self.live_room(connection)
        async with presence.lock:
            self.joined_room(connection)
            if presence.published_by == connection.peer_id:
                await self.stop_publisher(presence)
            elif self.sfu is not None:
                await self.sfu.remove(presence.code, connection.peer_id)

    async def update_media(
        self, db: AsyncSession, connection: Connection, media: MediaState
    ) -> None:
        presence = self.joined_room(connection)
        async with presence.lock:
            self.joined_room(connection)
            peer = presence.peers[connection.peer_id]
            new_share = media.screen and media.screen_stream_id != peer.media.screen_stream_id
            if new_share and (
                presence.mode == "livestream"
                or not (await self.settings.get(db)).allow_screen_share
            ):
                raise AuthError(ErrorCode.SCREEN_SHARE_DISABLED)
            if peer.media != media:
                peer.media = media
                await self.events.emit(
                    "media_state",
                    {"peer_id": peer.id, **media.model_dump()},
                    to=presence.code,
                    skip=peer.id,
                )

    async def mute_peer(
        self, connection: Connection, target: str, kind: Literal["audio", "video"]
    ) -> None:
        presence = self.joined_room(connection)
        async with presence.lock:
            self.joined_room(connection)
            if presence.host_id() != connection.peer_id:
                raise AuthError(ErrorCode.NOT_ROOM_HOST)
            if target == connection.peer_id or target not in presence.peers:
                raise AuthError(ErrorCode.PEER_NOT_FOUND)
            await self.events.emit(
                "force_mute", {"kind": kind, "by_peer_id": connection.peer_id}, to=target
            )

    async def kick(
        self,
        db: AsyncSession,
        code: str,
        *,
        peer_id: str | None,
        user_id: str | None = None,
        connection: Connection | None = None,
        actor: AuditActor | None = None,
        reason: str | None = None,
    ) -> None:
        room = await find_room(db, code)
        presence = self.state.get_room(code)
        if room.status != "active" or presence is None:
            raise AuthError(ErrorCode.PEER_NOT_FOUND)

        async with presence.lock:
            room = await find_room(db, code, locked=True)
            if room.status != "active":
                raise AuthError(ErrorCode.PEER_NOT_FOUND)
            old_host = presence.host_id()
            if connection is not None and old_host != connection.peer_id:
                raise AuthError(ErrorCode.NOT_ROOM_HOST)
            target = (
                presence.peers.get(peer_id)
                if peer_id
                else next(
                    (peer for peer in presence.peers.values() if peer.user_id == user_id), None
                )
            )
            if target is None:
                raise AuthError(ErrorCode.PEER_NOT_FOUND)

            if connection is not None:
                role = (
                    None
                    if target.connection.is_guest
                    else await db.scalar(select(User.role).where(User.id == UUID(target.user_id)))
                )
                if target.user_id == connection.user_id or role == "admin":
                    raise AuthError(ErrorCode.FORBIDDEN)
            if actor is not None:
                record_audit(
                    db, actor, "room.kick", "room", code, detail={"user_id": target.user_id}
                )
                await db.commit()
            presence.banned.add(target.user_id)
            await self.events.emit("kicked", {"reason": reason or "KICKED"}, to=target.id)
            await self.remove(presence, target, "kicked")
            self.metrics.room_kicks.inc()
            await self.host_changed(presence, old_host)

    async def close(
        self,
        db: AsyncSession,
        code: str,
        reason: Literal["host", "admin", "empty_timeout"],
        *,
        user_id: str | None = None,
        connection: Connection | None = None,
        actor: AuditActor | None = None,
        idle_before: datetime | None = None,
    ) -> None:
        room = await find_room(db, code)
        presence = self.state.get_room(code)
        if room.status == "closed" and presence is None:
            if reason == "host" and (
                connection is not None or room.host_id is None or str(room.host_id) != user_id
            ):
                raise AuthError(ErrorCode.NOT_ROOM_HOST)
            return
        presence = self.state.ensure_room(code, room.host_id, datetime.now(UTC), room.mode)
        async with presence.lock:
            room = await find_room(db, code, locked=True)
            if reason == "host":
                host = presence.host()
                allowed = (
                    host is not None and host.id == connection.peer_id
                    if connection is not None
                    else (room.host_id is not None and str(room.host_id) == user_id)
                    or (host is not None and host.user_id == user_id)
                )
                if not allowed:
                    raise AuthError(ErrorCode.NOT_ROOM_HOST)
            if idle_before is not None and (
                presence.peers or presence.empty_since is None or presence.empty_since > idle_before
            ):
                return
            if room.status != "closed":
                room.status = "closed"
                room.closed_reason = reason
                room.closed_at = datetime.now(UTC)
                if actor is not None:
                    record_audit(db, actor, "room.close", "room", code)
                await db.commit()
            await self.finish_close(presence, room.closed_reason or reason)

    async def finish_close(self, presence: RoomPresence, reason: str) -> None:
        if presence.mode == "livestream" and self.sfu is not None:
            await self.sfu.remove(presence.code)
        await self.events.emit("room_closed", {"reason": reason}, to=presence.code)
        for peer in list(presence.peers.values()):
            await self.events.leave(peer.id, presence.code)
        self.state.remove_room(presence)

    async def close_for_deleted_owner(
        self, db: AsyncSession, user_id: UUID, now: datetime
    ) -> list[str]:
        rows = await db.scalars(
            update(Room)
            .where(Room.host_id == user_id, Room.status == "active")
            .values(status="closed", closed_reason="owner_deleted", closed_at=now)
            .returning(Room.code)
        )
        return list(rows)

    async def sweep_empty(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        now = datetime.now(UTC)
        async with sessions() as db:
            settings = await self.settings.get(db)
            rows = await db.execute(
                select(Room.code, Room.host_id, Room.mode).where(Room.status == "active")
            )
            for code, owner, mode in rows.tuples():
                self.state.ensure_room(code, owner, now, mode)
        deadline = now - timedelta(seconds=settings.room_empty_ttl_seconds)
        for presence in self.state.list_rooms():
            presence.expire_seats(monotonic())
            if presence.empty_since is not None and presence.empty_since <= deadline:
                async with sessions() as db:
                    await self.close(db, presence.code, "empty_timeout", idle_before=deadline)

    async def admin_rooms(self, db: AsyncSession) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(Room, User.display_name)
            .outerjoin(User, Room.host_id == User.id)
            .where(Room.status == "active")
            .order_by(Room.created_at.desc(), Room.code)
        )
        rooms = []
        for room, owner_name in rows.tuples():
            presence = self.state.get_room(room.code)
            host = presence.host() if presence else None
            host_info = None
            if host is not None:
                host_info = {"id": host.user_id, "display_name": host.connection.display_name}
            elif room.host_id is not None:
                host_info = {"id": str(room.host_id), "display_name": owner_name}
            rooms.append(
                {
                    "code": room.code,
                    "name": room.name,
                    "mode": room.mode,
                    "host": host_info,
                    "participants": [
                        {**peer.public(), "joined_at": peer.joined_at}
                        for peer in presence.peers.values()
                    ]
                    if presence
                    else [],
                    "created_at": room.created_at,
                }
            )
        return rooms
