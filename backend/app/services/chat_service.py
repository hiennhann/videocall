import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from limits import parse
from sqlalchemy import Sequence, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AuthError, ErrorCode
from app.models import Message, Room, User
from app.realtime.state import Connection
from app.schemas.chat import ChatHistory, ChatMessage
from app.services.room_service import RoomService, find_room

logger = logging.getLogger(__name__)
CHAT_LIMIT = parse("5/3 second")


class ChatService:
    def __init__(self, rooms: RoomService) -> None:
        self.rooms = rooms
        self.pending: asyncio.Queue[Message] = asyncio.Queue(maxsize=256)

    async def send(
        self, sessions: async_sessionmaker[AsyncSession], connection: Connection, content: str
    ) -> dict[str, Any]:
        presence = self.rooms.joined_room(connection)
        async with presence.lock:
            self.rooms.joined_room(connection)
            async with sessions() as db:
                settings = await self.rooms.settings.get(db)
                if not settings.chat_enabled:
                    raise AuthError(ErrorCode.CHAT_DISABLED)
                if not self.rooms.limiter.hit(CHAT_LIMIT, "chat", connection.peer_id):
                    raise AuthError(ErrorCode.RATE_LIMITED)
                row = await db.execute(
                    select(Room.id, Sequence("messages_id_seq").next_value()).where(
                        Room.code == presence.code
                    )
                )
                room_id, message_id = row.one()
            msg = Message(
                id=message_id,
                room_id=room_id,
                user_id=None if connection.is_guest else UUID(connection.user_id),
                sender_name=connection.display_name,
                content=content,
                created_at=datetime.now(UTC),
            )
            payload = {
                "id": msg.id,
                "from": {
                    "peer_id": connection.peer_id,
                    "user_id": str(msg.user_id) if msg.user_id else None,
                    "display_name": msg.sender_name,
                },
                "text": msg.content,
                "ts": msg.created_at.isoformat(),
            }
            await self.rooms.events.emit("chat_message", payload, to=presence.code)
            if settings.chat_history_enabled:
                await self.pending.put(msg)
            return {"id": msg.id}

    async def store(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        while True:
            msg = await self.pending.get()
            try:
                async with sessions.begin() as db:
                    if msg.user_id is not None:
                        msg.user_id = await db.scalar(
                            select(User.id)
                            .where(User.id == msg.user_id)
                            .with_for_update(read=True, key_share=True)
                        )
                    db.add(msg)
            except (OSError, SQLAlchemyError):
                logger.warning(
                    "Không thể lưu tin nhắn vào lịch sử.", extra={"request_id": str(uuid4())}
                )
            finally:
                self.pending.task_done()

    async def history(
        self, db: AsyncSession, code: str, subject: str, before: int | None, limit: int
    ) -> ChatHistory:
        room = await find_room(db, code)
        if room.host_id is None or subject != str(room.host_id):
            presence = self.rooms.state.get_room(code)
            if (
                room.status != "active"
                or presence is None
                or not any(peer.user_id == subject for peer in presence.peers.values())
            ):
                raise AuthError(ErrorCode.NOT_IN_ROOM)
        if not (await self.rooms.settings.get(db)).chat_history_enabled:
            return ChatHistory(items=[])

        query = select(Message).where(Message.room_id == room.id)
        if before is not None:
            query = query.where(Message.id < before)
        rows = list(await db.scalars(query.order_by(Message.id.desc()).limit(limit + 1)))
        return ChatHistory(
            items=[ChatMessage.model_validate(message) for message in rows[:limit]],
            next_before=rows[limit - 1].id if len(rows) > limit else None,
        )
