import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, delete, exists, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AuthError, ErrorCode
from app.models import CallParticipant, Message, Room, RoomInvite, User
from app.schemas.friends import avatar_url
from app.services.user_service import editable_user

logger = logging.getLogger(__name__)


def seconds(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds()))


class CallHistory:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.pending: asyncio.Queue = asyncio.Queue(maxsize=4096)

    def queue(self, action: str, participant: CallParticipant, reason: str | None = None) -> None:
        try:
            self.pending.put_nowait((action, participant, datetime.now(UTC), reason))
        except asyncio.QueueFull:
            logger.warning("call_history_queue_full")

    async def recover(self, db: AsyncSession) -> None:
        await db.execute(
            update(CallParticipant)
            .where(CallParticipant.left_at.is_(None))
            .values(
                left_at=func.greatest(
                    CallParticipant.joined_at,
                    func.coalesce(
                        select(Room.closed_at)
                        .where(Room.id == CallParticipant.room_id)
                        .scalar_subquery(),
                        func.now(),
                    ),
                ),
                leave_reason="server_restart",
            )
        )
        await db.commit()

    async def store(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        while True:
            action, row, timestamp, reason = await self.pending.get()
            try:
                async with sessions.begin() as db:
                    if action == "join":
                        if row.user_id is not None:
                            row.user_id = await db.scalar(
                                select(User.id)
                                .where(User.id == row.user_id)
                                .with_for_update(read=True, key_share=True)
                            )
                        db.add(row)
                    elif row.id is not None:
                        await db.execute(
                            update(CallParticipant)
                            .where(CallParticipant.id == row.id)
                            .values(left_at=timestamp, leave_reason=reason)
                        )
            except (OSError, SQLAlchemyError):
                logger.warning("call_history_write_failed")
            finally:
                self.pending.task_done()

    async def require_read(self, db: AsyncSession, actor: UUID) -> None:
        await editable_user(db, actor)
        if not (await self.settings.get(db)).call_history_enabled:
            raise AuthError(ErrorCode.FEATURE_DISABLED)

    @staticmethod
    def mine(actor: UUID):
        return exists().where(CallParticipant.room_id == Room.id, CallParticipant.user_id == actor)

    @staticmethod
    def missed(actor: UUID):
        return exists().where(
            RoomInvite.room_id == Room.id,
            RoomInvite.invitee_id == actor,
            RoomInvite.expires_at <= func.now(),
            RoomInvite.status.in_(["pending", "expired"]),
        )

    async def listing(
        self, db: AsyncSession, actor: UUID | None, kind, start, end, page, page_size, host=None
    ) -> dict:
        joined_at = (
            select(func.min(CallParticipant.joined_at))
            .where(CallParticipant.room_id == Room.id)
            .correlate(Room)
            .scalar_subquery()
        )
        if actor is None:
            query = select(Room).where(Room.status == "closed", joined_at.is_not(None))
            if host is not None:
                query = query.where(Room.host_id == host)
            started = joined_at
        else:
            await self.require_read(db, actor)
            mine, missed = self.mine(actor), self.missed(actor)
            query = select(Room).where(or_(mine, missed))
            missed_at = (
                select(func.max(RoomInvite.expires_at))
                .where(
                    RoomInvite.room_id == Room.id,
                    RoomInvite.invitee_id == actor,
                    RoomInvite.status.in_(["pending", "expired"]),
                    RoomInvite.expires_at <= func.now(),
                )
                .correlate(Room)
                .scalar_subquery()
            )
            started = case((mine, joined_at), else_=missed_at)
            if kind == "hosted":
                query = query.where(mine, Room.host_id == actor)
            elif kind == "joined":
                query = query.where(mine, Room.host_id.is_distinct_from(actor))
            elif kind == "missed_invite":
                query = query.where(~mine, missed)
        if start:
            query = query.where(started >= start)
        if end:
            query = query.where(started <= end)
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        rooms = list(
            await db.scalars(
                query.order_by(started.desc(), Room.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        items = [await self.summary(db, room, actor) for room in rooms]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def detail(self, db: AsyncSession, code: str, actor: UUID | None) -> dict:
        query = select(Room).where(Room.code == code)
        if actor is not None:
            await self.require_read(db, actor)
            query = query.where(or_(self.mine(actor), self.missed(actor)))
        else:
            query = query.where(
                Room.status == "closed", exists().where(CallParticipant.room_id == Room.id)
            )
        room = await db.scalar(query)
        if room is None:
            raise AuthError(ErrorCode.HISTORY_NOT_FOUND)
        return await self.summary(db, room, actor, detail=True)

    async def summary(
        self, db: AsyncSession, room: Room, actor: UUID | None, *, detail: bool = False
    ) -> dict:
        base = {"room_code": room.code, "name": room.name}
        if actor is not None and not await db.scalar(
            select(self.mine(actor)).select_from(Room).where(Room.id == room.id)
        ):
            missed_at = await db.scalar(
                select(func.max(RoomInvite.expires_at)).where(
                    RoomInvite.room_id == room.id,
                    RoomInvite.invitee_id == actor,
                    RoomInvite.status.in_(["pending", "expired"]),
                    RoomInvite.expires_at <= func.now(),
                )
            )
            result = {
                **base,
                "type": "missed_invite",
                "started_at": missed_at,
                "ended_at": None,
                "duration_seconds": 0,
                "my_duration_seconds": 0,
                "participants_count": 0,
                "participants_preview": [],
                "chat_available": False,
            }
            return {**result, "participants": []} if detail else result

        rows = list(
            (
                await db.execute(
                    select(CallParticipant, User)
                    .outerjoin(User, User.id == CallParticipant.user_id)
                    .where(CallParticipant.room_id == room.id)
                    .order_by(CallParticipant.joined_at, CallParticipant.id)
                )
            ).all()
        )
        now = datetime.now(UTC)
        start = rows[0][0].joined_at if rows else room.created_at
        end = (
            None
            if any(p.left_at is None for p, _ in rows)
            else max((p.left_at for p, _ in rows), default=room.closed_at)
        )
        unique = {}
        for p, user in rows:
            unique.setdefault(
                p.user_id or p.id,
                {"display_name": p.display_name, "avatar_url": avatar_url(user) if user else None},
            )
        result = {
            **base,
            "started_at": start,
            "ended_at": end,
            "duration_seconds": seconds(start, end or now),
            "participants_count": len(unique),
            "participants_preview": list(unique.values())[:4],
        }
        if actor is None:
            host = await db.get(User, room.host_id) if room.host_id else None
            result["host"] = {"id": host.id, "display_name": host.display_name} if host else None
        else:
            result.update(
                type="hosted" if room.host_id == actor else "joined",
                my_duration_seconds=sum(
                    seconds(p.joined_at, p.left_at or now) for p, _ in rows if p.user_id == actor
                ),
                chat_available=bool(
                    await db.scalar(
                        select(exists(self.chat_query(room.id, await self.settings.get(db))))
                    )
                ),
            )
        if detail:
            result["participants"] = [
                {
                    "display_name": p.display_name,
                    "is_guest": p.is_guest,
                    "joined_at": p.joined_at,
                    "left_at": p.left_at,
                    "leave_reason": p.leave_reason,
                }
                for p, _ in rows
            ]
        return result

    @staticmethod
    def chat_query(room_id: UUID, policy):
        return select(Message).where(
            Message.room_id == room_id,
            Message.created_at >= datetime.now(UTC) - timedelta(days=policy.chat_retention_days),
        )

    async def export(self, db: AsyncSession, code: str, actor: UUID):
        await self.require_read(db, actor)
        room_id = await db.scalar(select(Room.id).where(Room.code == code, self.mine(actor)))
        if room_id is None:
            raise AuthError(ErrorCode.HISTORY_NOT_FOUND)
        query = self.chat_query(room_id, await self.settings.get(db))
        if not await db.scalar(select(exists(query))):
            raise AuthError(ErrorCode.HISTORY_NOT_FOUND)

        async def lines():
            rows = await db.stream_scalars(query.order_by(Message.id))
            try:
                async for msg in rows:
                    yield f"[{msg.created_at.isoformat()}] {msg.sender_name}: {msg.content}\n"
            finally:
                await rows.close()

        return lines()

    async def clear(self, db: AsyncSession, actor: UUID) -> None:
        await editable_user(db, actor)
        await self.pending.join()
        await db.execute(
            update(CallParticipant).where(CallParticipant.user_id == actor).values(user_id=None)
        )
        await db.execute(
            delete(RoomInvite).where(
                RoomInvite.invitee_id == actor,
                RoomInvite.expires_at <= func.now(),
                RoomInvite.status.in_(["pending", "expired"]),
            )
        )
        await db.commit()

    async def prune(self, db: AsyncSession) -> None:
        policy = await self.settings.get(db)
        now = datetime.now(UTC)
        history_deadline = now - timedelta(days=policy.call_history_retention_days)
        chat_deadline = now - timedelta(days=policy.chat_retention_days)
        await db.execute(
            delete(Message).where(
                Message.created_at < chat_deadline,
                Message.room_id.in_(select(Room.id).where(Room.status == "closed")),
            )
        )
        old_history = select(Room.id).where(Room.closed_at < history_deadline)
        await db.execute(delete(CallParticipant).where(CallParticipant.room_id.in_(old_history)))
        await db.execute(delete(RoomInvite).where(RoomInvite.room_id.in_(old_history)))
        await db.execute(delete(Room).where(Room.closed_at < min(history_deadline, chat_deadline)))
        await db.commit()
