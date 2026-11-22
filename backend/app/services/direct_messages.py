from datetime import UTC, datetime, timedelta
from uuid import UUID

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.models import Conversation, DirectMessage, User
from app.schemas.direct_messages import DirectSend
from app.schemas.friends import PublicUser
from app.services.friend_service import are_friends, canonical_pair
from app.services.user_service import editable_user

SEND_LIMIT = parse("10/10 seconds")
TYPING_LIMIT = parse("1/2 seconds")


class DirectMessages:
    def __init__(self, settings, notify, metrics) -> None:
        self.settings, self.notify, self.metrics = settings, notify, metrics
        self.limiter = FixedWindowRateLimiter(MemoryStorage())

    @staticmethod
    def message(row: DirectMessage) -> dict:
        return {
            "id": row.id,
            "sender_id": str(row.sender_id) if row.sender_id else None,
            "client_msg_id": str(row.client_msg_id),
            "text": row.content if row.deleted_at is None else None,
            "created_at": row.created_at.isoformat(),
            "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        }

    @staticmethod
    def other(conversation: Conversation, actor: UUID) -> UUID:
        return conversation.user_b_id if actor == conversation.user_a_id else conversation.user_a_id

    async def require_conversation(
        self, db: AsyncSession, actor: UUID, conversation_id: UUID, *, locked=False
    ) -> Conversation:
        await editable_user(db, actor)
        query = select(Conversation).where(
            Conversation.id == conversation_id,
            or_(Conversation.user_a_id == actor, Conversation.user_b_id == actor),
        )
        conversation = await db.scalar(query.with_for_update() if locked else query)
        if conversation is None:
            raise AuthError(ErrorCode.NOT_IN_CONVERSATION)
        return conversation

    @staticmethod
    def pair_query(actor: UUID, target: UUID):
        first, second = canonical_pair(actor, target)
        return select(Conversation).where(
            Conversation.user_a_id == first, Conversation.user_b_id == second
        )

    async def send(self, db: AsyncSession, actor: UUID, body: DirectSend, sid: str) -> dict:
        target = body.to_user_id
        # Cùng thứ tự khóa với kết bạn/chặn và gửi lời mời gọi.
        await db.execute(
            select(User.id).where(User.id.in_([actor, target])).order_by(User.id).with_for_update()
        )
        await editable_user(db, actor)
        conversation = await db.scalar(self.pair_query(actor, target).with_for_update())
        if conversation:
            existing = await db.scalar(
                select(DirectMessage).where(
                    DirectMessage.conversation_id == conversation.id,
                    DirectMessage.sender_id == actor,
                    DirectMessage.client_msg_id == body.client_msg_id,
                )
            )
            if existing:
                return {"conversation_id": str(conversation.id), "message": self.message(existing)}
        if not (await self.settings.get(db)).dm_enabled:
            raise AuthError(ErrorCode.DM_DISABLED)
        user = await db.get(User, target)
        if user is None or not user.is_active or not await are_friends(db, actor, target):
            raise AuthError(ErrorCode.NOT_FRIENDS)
        if not self.limiter.hit(SEND_LIMIT, "dm_send", str(actor)):
            raise AuthError(ErrorCode.RATE_LIMITED)
        if conversation is None:
            first, second = canonical_pair(actor, target)
            conversation = Conversation(user_a_id=first, user_b_id=second)
            db.add(conversation)
            await db.flush()
        row = DirectMessage(
            conversation_id=conversation.id,
            sender_id=actor,
            client_msg_id=body.client_msg_id,
            content=body.text,
        )
        db.add(row)
        await db.flush()
        conversation.last_message_id, conversation.last_message_at = row.id, row.created_at
        await db.commit()
        self.metrics.dm_messages.inc()
        payload = {"conversation_id": str(conversation.id), "message": self.message(row)}
        await self.notify("dm_message", payload, target)
        await self.notify("dm_message", payload, actor, skip=sid)
        return payload

    async def summary(self, db: AsyncSession, actor: UUID, conversation: Conversation) -> dict:
        peer_id = self.other(conversation, actor)
        user = await db.get(User, peer_id)
        last = (
            await db.get(DirectMessage, conversation.last_message_id)
            if conversation.last_message_id
            else None
        )
        last_read = (
            conversation.a_last_read_id
            if actor == conversation.user_a_id
            else conversation.b_last_read_id
        )
        unread = await db.scalar(
            select(func.count())
            .select_from(DirectMessage)
            .where(
                DirectMessage.conversation_id == conversation.id,
                DirectMessage.sender_id == peer_id,
                DirectMessage.id > last_read,
                DirectMessage.deleted_at.is_(None),
            )
        )
        preview = self.message(last) if last else None
        if preview and preview["text"] is not None:
            preview["text"] = preview["text"][:120]
        policy = await self.settings.get(db)
        return {
            "id": conversation.id,
            "user": PublicUser.from_user(user) if user else None,
            "last_message": preview,
            "last_message_at": conversation.last_message_at,
            "unread_count": unread,
            "last_read_id": last_read,
            "peer_last_read_id": conversation.b_last_read_id
            if actor == conversation.user_a_id
            else conversation.a_last_read_id,
            "can_send": bool(
                policy.dm_enabled
                and user
                and user.is_active
                and await are_friends(db, actor, peer_id)
            ),
        }

    async def listing(self, db: AsyncSession, actor: UUID, page: int, page_size: int) -> dict:
        await editable_user(db, actor)
        query = select(Conversation).where(
            or_(Conversation.user_a_id == actor, Conversation.user_b_id == actor)
        )
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        rows = list(
            await db.scalars(
                query.order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return {
            "items": [await self.summary(db, actor, row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def with_user(self, db: AsyncSession, actor: UUID, target: UUID) -> dict:
        await editable_user(db, actor)
        conversation = await db.scalar(self.pair_query(actor, target))
        if conversation:
            return await self.summary(db, actor, conversation)
        user = await db.get(User, target)
        if user is None or not user.is_active or not await are_friends(db, actor, target):
            raise AuthError(ErrorCode.NOT_FRIENDS)
        return {
            "id": None,
            "user": PublicUser.from_user(user),
            "last_message": None,
            "last_message_at": None,
            "unread_count": 0,
            "last_read_id": 0,
            "peer_last_read_id": 0,
            "can_send": (await self.settings.get(db)).dm_enabled,
        }

    async def history(
        self,
        db: AsyncSession,
        actor: UUID,
        conversation_id: UUID,
        before: int | None,
        after: int | None,
        limit: int,
    ) -> dict:
        await self.require_conversation(db, actor, conversation_id)
        query = select(DirectMessage).where(DirectMessage.conversation_id == conversation_id)
        if before is not None:
            query = query.where(DirectMessage.id < before)
        if after is not None:
            query = query.where(DirectMessage.id > after)
        rows = list(
            await db.scalars(
                query.order_by(
                    DirectMessage.id if after is not None else DirectMessage.id.desc()
                ).limit(limit + 1)
            )
        )
        cursor = rows[limit - 1].id if len(rows) > limit else None
        return {
            "items": [self.message(row) for row in rows[:limit]],
            "next_before": cursor if after is None else None,
            "next_after": cursor if after is not None else None,
        }

    async def read(
        self, db: AsyncSession, actor: UUID, conversation_id: UUID, up_to_id: int
    ) -> None:
        conversation = await self.require_conversation(db, actor, conversation_id, locked=True)
        mark = await db.scalar(
            select(func.max(DirectMessage.id)).where(
                DirectMessage.conversation_id == conversation.id, DirectMessage.id <= up_to_id
            )
        )
        field = "a_last_read_id" if actor == conversation.user_a_id else "b_last_read_id"
        if mark is None or mark <= getattr(conversation, field):
            return
        setattr(conversation, field, mark)
        await db.commit()
        await self.notify(
            "dm_read",
            {"conversation_id": str(conversation.id), "by_user_id": str(actor), "up_to_id": mark},
            self.other(conversation, actor),
        )

    async def remove(
        self, db: AsyncSession, actor: UUID, conversation_id: UUID, message_id: int
    ) -> None:
        conversation = await self.require_conversation(db, actor, conversation_id, locked=True)
        row = await db.scalar(
            select(DirectMessage).where(
                DirectMessage.id == message_id,
                DirectMessage.conversation_id == conversation.id,
                DirectMessage.sender_id == actor,
            )
        )
        if row is None:
            raise AuthError(ErrorCode.MESSAGE_NOT_FOUND)
        if row.deleted_at is None:
            row.content, row.deleted_at = "", datetime.now(UTC)
            await db.commit()
            payload = {"conversation_id": str(conversation.id), "message": self.message(row)}
            for recipient in (actor, self.other(conversation, actor)):
                await self.notify("dm_message", payload, recipient)

    async def typing(self, db: AsyncSession, actor: UUID, target: UUID, typing: bool) -> None:
        await editable_user(db, actor)
        if not self.limiter.hit(TYPING_LIMIT, "dm_typing", str(actor)):
            return
        if (await self.settings.get(db)).dm_enabled and await are_friends(db, actor, target):
            await self.notify(
                "dm_typing",
                {"to_user_id": str(target), "from_user_id": str(actor), "typing": typing},
                target,
            )

    async def prune(self, db: AsyncSession) -> None:
        days = (await self.settings.get(db)).dm_retention_days
        if not days:
            return
        old = DirectMessage.created_at < datetime.now(UTC) - timedelta(days=days)
        await db.execute(
            select(Conversation.id)
            .where(Conversation.id.in_(select(DirectMessage.conversation_id).where(old)))
            .order_by(Conversation.id)
            .with_for_update()
        )
        await db.execute(delete(DirectMessage).where(old))
        latest = (
            select(DirectMessage.id)
            .where(DirectMessage.conversation_id == Conversation.id)
            .order_by(DirectMessage.id.desc())
            .limit(1)
            .correlate(Conversation)
            .scalar_subquery()
        )
        latest_at = (
            select(DirectMessage.created_at).where(DirectMessage.id == latest).scalar_subquery()
        )
        await db.execute(
            update(Conversation)
            .where(
                Conversation.last_message_id.is_not(None),
                ~select(DirectMessage.id)
                .where(DirectMessage.id == Conversation.last_message_id)
                .exists(),
            )
            .values(last_message_id=latest, last_message_at=latest_at)
        )
        await db.commit()
