import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import partial
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

import socketio
from asyncpg import PostgresError
from limits import parse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.contextvars import bound_contextvars

from app.api.errors import AUTH_ERRORS
from app.core.errors import AuthError, ErrorCode
from app.core.security import decode_access_token
from app.metrics import Metrics
from app.models import Room
from app.realtime.state import Connection, RoomStateStore
from app.schemas.chat import SendMessage
from app.schemas.rooms import (
    JoinRoom,
    KickPeer,
    MediaState,
    MutePeer,
    PeerTarget,
    SessionDescription,
    SignalCandidate,
    SignalDescription,
)
from app.services.account_events import AccountEvents
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.room_service import RoomService
from app.services.settings_service import SettingsService
from app.sfu.control import SfuClient

logger = logging.getLogger(__name__)
RATE_VIOLATIONS = parse("4/minute")
type Handler = Callable[[Connection, Any], Awaitable[dict[str, Any] | None]]


def error_payload(code: ErrorCode) -> dict[str, str]:
    return {"code": code.value, "message": AUTH_ERRORS[code][1]}


class RealtimeServer(AccountEvents):
    def __init__(
        self, origins: list[str], settings: SettingsService, sfu: SfuClient | None, metrics: Metrics
    ) -> None:
        self.sio = socketio.AsyncServer(
            async_mode="asgi",
            cors_allowed_origins=origins,
            ping_interval=25,
            ping_timeout=20,
            max_http_buffer_size=32 * 1024,
        )
        self.state = RoomStateStore()
        self.metrics = metrics
        self.rooms = RoomService(settings, self.state, self, metrics, sfu)
        self.chat = ChatService(self.rooms)
        self._sweeper: asyncio.Task[None] | None = None
        self._chat_writer: asyncio.Task[None] | None = None
        self.sio.on("connect", self.connect)
        self.sio.on("disconnect", self.disconnect)
        self._bind("join_room", self.join)
        self._bind("leave_room", self.leave_room)
        for event in ("offer", "answer", "ice_candidate"):
            self._bind(event, partial(self.signal, event))
        self._bind("chat_message", self.chat_message)
        self._bind("media_state", self.media_state)
        self._bind("mute_peer", self.mute_peer)
        self._bind("subscribe", self.subscribe)
        self._bind("unsubscribe", self.unsubscribe)
        self._bind("promote_speaker", self.promote_speaker)
        self._bind("demote_speaker", self.demote_speaker)
        self._bind("kick", self.kick)
        self._bind("transfer_host", self.transfer)
        self._bind("close_room", self.close_room)

    def start(self, sessions: async_sessionmaker[AsyncSession], auth: AuthService) -> None:
        self.sessions = sessions
        self.auth = auth
        self._sweeper = asyncio.create_task(self.sweep())
        self._chat_writer = asyncio.create_task(self.chat.store(sessions))

    async def stop(self) -> None:
        if self._sweeper is not None:
            self._sweeper.cancel()
            await asyncio.gather(self._sweeper, return_exceptions=True)
        await self.sio.shutdown()
        if self._chat_writer is not None:
            await self.chat.pending.join()
            self._chat_writer.cancel()
            await asyncio.gather(self._chat_writer, return_exceptions=True)
        if self.rooms.sfu is not None:
            await self.rooms.sfu.http.aclose()

    async def sweep(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                await self.rooms.sweep_empty(self.sessions)
            except (OSError, PostgresError, SQLAlchemyError):
                logger.warning("Chưa thể kiểm tra phòng trống.", extra={"request_id": str(uuid4())})

    async def connect(self, sid: str, environ: dict[str, Any], auth: object = None) -> None:
        request_id = str(uuid4())
        self.metrics.socket_events.labels("connect").inc()
        try:
            token = auth.get("token") if isinstance(auth, dict) else None
            if not isinstance(token, str) or not token or len(token) > 4096:
                raise AuthError(ErrorCode.UNAUTHENTICATED)
            access = decode_access_token(token, self.auth.secret)
            identity = access.identity
            peer_ip = environ.get("REMOTE_ADDR") or "unknown"
            async with self.sessions.begin() as db:
                if identity.family_id is None:
                    if not (await self.rooms.settings.get(db)).allow_guest:
                        raise AuthError(ErrorCode.GUEST_DISABLED)
                    name, role = identity.display_name, "guest"
                else:
                    user = await AuthService.lock_user(db, identity.id)
                    if user is None:
                        raise AuthError(ErrorCode.TOKEN_INVALID)
                    if not user.is_active:
                        raise AuthError(ErrorCode.ACCOUNT_DISABLED)
                    if user.must_change_password:
                        raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
                    if not await AuthService.has_active_session(db, user.id, identity.family_id):
                        raise AuthError(ErrorCode.TOKEN_INVALID)
                    name, role = user.display_name, user.role

                self.state.add_connection(
                    Connection(sid, identity.subject, name, role, identity.family_id, peer_ip)
                )
            logger.info(
                "socket_connected", extra={"request_id": request_id, "user_id": identity.subject}
            )
        except AuthError as exc:
            self.record_socket_error("connect", exc.code, request_id)
            payload = error_payload(exc.code)
            payload["request_id"] = request_id
            raise socketio.exceptions.ConnectionRefusedError(payload["message"], payload) from None
        except (OSError, PostgresError, SQLAlchemyError):
            self.state.remove_connection(sid)
            self.record_socket_error("connect", "INTERNAL_ERROR", request_id)
            raise socketio.exceptions.ConnectionRefusedError(
                "Không thể xác thực kết nối.",
                {
                    "code": "INTERNAL_ERROR",
                    "message": "Không thể xác thực kết nối.",
                    "request_id": request_id,
                },
            ) from None

    async def disconnect(self, sid: str, reason: str) -> None:
        self.metrics.socket_events.labels("disconnect").inc()
        connection = self.state.get_connection(sid)
        if connection is not None:
            async with connection.lock:
                try:
                    await self.rooms.leave(
                        connection,
                        "disconnected",
                        reserve=reason
                        in {self.sio.reason.TRANSPORT_CLOSE, self.sio.reason.PING_TIMEOUT},
                    )
                finally:
                    self.state.remove_connection(sid)
                    logger.info(
                        "socket_disconnected",
                        extra={"request_id": str(uuid4()), "user_id": connection.user_id},
                    )

    def record_socket_error(self, name: str, code: str, request_id: str) -> None:
        self.metrics.socket_errors.labels(code).inc()
        logger.log(
            logging.ERROR if code == "INTERNAL_ERROR" else logging.WARNING,
            "socket_error",
            extra={"socket_event": name, "code": code, "request_id": request_id},
        )

    def _bind(self, name: str, handler: Handler) -> None:
        async def dispatch(sid: str, data: Any, extra: tuple[Any, ...]) -> dict[str, Any]:
            connection = self.state.get_connection(sid)
            if connection is None:
                return {"ok": False, "error": error_payload(ErrorCode.UNAUTHENTICATED)}
            try:
                if extra:
                    raise AuthError(ErrorCode.INVALID_PAYLOAD)
                async with connection.lock:
                    if self.state.get_connection(sid) is not connection:
                        raise AuthError(ErrorCode.UNAUTHENTICATED)
                    result = await handler(connection, data)
                return {"ok": True, "data": result} if result is not None else {"ok": True}
            except ValidationError:
                return {"ok": False, "error": error_payload(ErrorCode.INVALID_PAYLOAD)}
            except AuthError as exc:
                if exc.code == ErrorCode.RATE_LIMITED and not self.rooms.limiter.hit(
                    RATE_VIOLATIONS, "violations", sid
                ):
                    self.sio.start_background_task(self.sio.disconnect, sid)
                return {"ok": False, "error": error_payload(exc.code)}
            except Exception:
                return {
                    "ok": False,
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Không thể xử lý sự kiện.",
                    },
                }

        async def event(sid: str, data: Any = None, *extra: Any) -> dict[str, Any]:
            request_id = str(uuid4())
            connection = self.state.get_connection(sid)
            self.metrics.socket_events.labels(name).inc()
            started = perf_counter()
            with bound_contextvars(
                request_id=request_id, user_id=connection.user_id if connection else None
            ):
                try:
                    result = await dispatch(sid, data, extra)
                    if not result["ok"]:
                        error = result["error"]
                        error["request_id"] = request_id
                        self.record_socket_error(name, error["code"], request_id)
                    elif name in {"join_room", "leave_room", "kick", "close_room"}:
                        logger.info("socket_event", extra={"socket_event": name})
                    return result
                finally:
                    if name == "join_room":
                        self.metrics.join_latency.observe(perf_counter() - started)

        self.sio.on(name, event)

    async def join(self, connection: Connection, data: Any) -> dict[str, Any]:
        request = JoinRoom.model_validate(data)
        password = request.password.get_secret_value() if request.password is not None else None
        async with self.sessions() as db:
            return await self.rooms.join(db, connection, request.code, password)

    async def leave_room(self, connection: Connection, data: Any) -> None:
        if data not in (None, {}):
            raise AuthError(ErrorCode.INVALID_PAYLOAD)
        self.rooms.joined_room(connection)
        await self.rooms.leave(connection)

    async def signal(self, event: str, connection: Connection, data: Any) -> dict[str, Any] | None:
        if event == "ice_candidate":
            ice = SignalCandidate.model_validate(data)
            value = ice.candidate
            max_bytes = 2048
            target = ice.to
            key = "candidate"
        else:
            description = SignalDescription.model_validate(data)
            if description.sdp.type != event:
                raise AuthError(ErrorCode.INVALID_PAYLOAD)
            value = description.sdp
            max_bytes = 20 * 1024
            target = description.to
            key = "sdp"
        if len(value.model_dump_json(exclude_unset=True).encode()) > max_bytes:
            raise AuthError(ErrorCode.INVALID_PAYLOAD)
        if target == "sfu":
            if event != "offer":
                raise AuthError(ErrorCode.INVALID_PAYLOAD)
            answer = await self.rooms.live_offer(connection, "publish", description.sdp)
            return answer.model_dump()
        await self.rooms.signal(
            connection, target, event, {key: value.model_dump(exclude_unset=True)}
        )
        return None

    async def subscribe(self, connection: Connection, data: Any) -> dict[str, Any]:
        sdp = SessionDescription.model_validate(data)
        if sdp.type != "offer" or len(sdp.sdp.encode()) > 20 * 1024:
            raise AuthError(ErrorCode.INVALID_PAYLOAD)
        return (await self.rooms.live_offer(connection, "view", sdp)).model_dump()

    async def unsubscribe(self, connection: Connection, data: Any) -> None:
        if data not in (None, {}):
            raise AuthError(ErrorCode.INVALID_PAYLOAD)
        await self.rooms.leave_stream(connection)

    async def promote_speaker(self, connection: Connection, data: Any) -> None:
        request = PeerTarget.model_validate(data)
        await self.rooms.select_speaker(connection, request.peer_id)

    async def demote_speaker(self, connection: Connection, data: Any) -> None:
        if data not in (None, {}):
            raise AuthError(ErrorCode.INVALID_PAYLOAD)
        await self.rooms.select_speaker(connection, None)

    async def kick(self, connection: Connection, data: Any) -> None:
        request = KickPeer.model_validate(data)
        presence = self.rooms.joined_room(connection)
        async with self.sessions() as db:
            await self.rooms.kick(
                db,
                presence.code,
                peer_id=request.peer_id,
                connection=connection,
                reason=request.reason,
            )

    async def chat_message(self, connection: Connection, data: Any) -> dict[str, Any]:
        request = SendMessage.model_validate(data)
        return await self.chat.send(self.sessions, connection, request.text)

    async def media_state(self, connection: Connection, data: Any) -> None:
        request = MediaState.model_validate(data)
        async with self.sessions() as db:
            await self.rooms.update_media(db, connection, request)

    async def mute_peer(self, connection: Connection, data: Any) -> None:
        request = MutePeer.model_validate(data)
        await self.rooms.mute_peer(connection, request.peer_id, request.kind)

    async def transfer(self, connection: Connection, data: Any) -> None:
        request = PeerTarget.model_validate(data)
        await self.rooms.transfer_host(connection, request.peer_id)

    async def close_room(self, connection: Connection, data: Any) -> None:
        if data not in (None, {}):
            raise AuthError(ErrorCode.INVALID_PAYLOAD)
        presence = self.rooms.joined_room(connection)
        async with self.sessions() as db:
            await self.rooms.close(db, presence.code, "host", connection=connection)

    async def emit(
        self, event: str, payload: dict[str, Any], *, to: str, skip: str | None = None
    ) -> None:
        await self.sio.emit(event, payload, to=to, skip_sid=skip)

    async def enter(self, peer_id: str, code: str) -> None:
        await self.sio.enter_room(peer_id, code)

    async def leave(self, peer_id: str, code: str) -> None:
        await self.sio.leave_room(peer_id, code)

    async def sessions_revoked(
        self,
        user_id: UUID,
        reason: str,
        *,
        only_family: UUID | None = None,
        keep_family: UUID | None = None,
    ) -> None:
        for connection in self.state.connections_for(str(user_id)):
            if only_family is not None and connection.family_id != only_family:
                continue
            if keep_family is not None and connection.family_id == keep_family:
                continue
            await self.emit("force_disconnect", {"reason": reason}, to=connection.peer_id)
            await self.sio.disconnect(connection.peer_id)

    async def close_owned_rooms(self, db: AsyncSession, user_id: UUID, now: datetime) -> list[str]:
        return await self.rooms.close_for_deleted_owner(db, user_id, now)

    async def owned_rooms_closed(self, codes: list[str]) -> None:
        for code in codes:
            presence = self.state.get_room(code)
            if presence is not None:
                async with presence.lock:
                    await self.rooms.finish_close(presence, "owner_deleted")

    def is_online(self, user_id: UUID) -> bool:
        return bool(self.state.connections_for(str(user_id)))

    async def room_counts(self, db: AsyncSession) -> tuple[int, int, int]:
        active = await db.scalar(
            select(func.count()).select_from(Room).where(Room.status == "active")
        )
        return (
            self.state.connection_count(),
            active or 0,
            sum(len(room.peers) for room in self.state.list_rooms()),
        )
