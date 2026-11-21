from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID

from sqlalchemy import and_, case, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import AuthError, ErrorCode
from app.models import FriendRequest, Friendship, RoomInvite, User, UserBlock
from app.schemas.friends import (
    BlockItem,
    FriendItem,
    FriendPage,
    PublicUser,
    RequestItem,
    SearchUser,
)
from app.schemas.settings import SettingsSchema
from app.services.friend_events import FriendEvents
from app.services.settings_service import SettingsService
from app.services.user_service import editable_user


def canonical_pair(first: UUID, second: UUID) -> tuple[UUID, UUID]:
    return min(first, second), max(first, second)


async def are_friends(db: AsyncSession, first: UUID, second: UUID) -> bool:
    return await db.get(
        Friendship, canonical_pair(first, second)
    ) is not None and not await db.scalar(select(blocked_between(first, second)))


def blocked_between(first, second):
    return exists().where(
        or_(
            and_(UserBlock.blocker_id == first, UserBlock.blocked_id == second),
            and_(UserBlock.blocker_id == second, UserBlock.blocked_id == first),
        )
    )


def friend_users(user_id: UUID):
    other = case(
        (Friendship.user_a_id == user_id, Friendship.user_b_id), else_=Friendship.user_a_id
    )
    return (
        select(User, Friendship.created_at)
        .join(Friendship, User.id == other)
        .where(
            or_(Friendship.user_a_id == user_id, Friendship.user_b_id == user_id),
            User.is_active.is_(True),
            ~blocked_between(user_id, User.id),
        )
    )


def request_item(request: FriendRequest, sender: User, recipient: User) -> RequestItem:
    return RequestItem(
        id=request.id,
        from_user=PublicUser.from_user(sender),
        to=PublicUser.from_user(recipient),
        created_at=request.created_at,
        status="accepted" if request.status == "accepted" else "pending",
    )


def latest_sent(user_id: UUID):
    return (
        select(FriendRequest.id)
        .where(FriendRequest.from_user_id == user_id)
        .distinct(FriendRequest.to_user_id)
        .order_by(
            FriendRequest.to_user_id, FriendRequest.created_at.desc(), FriendRequest.id.desc()
        )
    )


class FriendService:
    async def _cancel_call_invites(
        self, db: AsyncSession, actor: UUID, target: UUID
    ) -> list[RoomInvite]:
        pair = (actor, target)
        return list(
            await db.scalars(
                update(RoomInvite)
                .where(
                    RoomInvite.inviter_id.in_(pair),
                    RoomInvite.invitee_id.in_(pair),
                    RoomInvite.status == "pending",
                )
                .values(
                    status=case(
                        (RoomInvite.expires_at <= func.now(), "expired"), else_="cancelled"
                    ),
                    responded_at=func.now(),
                )
                .returning(RoomInvite)
            )
        )

    def __init__(self, settings: SettingsService, events: FriendEvents) -> None:
        self.settings = settings
        self.events = events

    async def _policy(
        self, db: AsyncSession, actor: UUID | None, *, enabled: bool = True
    ) -> SettingsSchema:
        await editable_user(db, actor)
        policy = await self.settings.get(db)
        if enabled and not policy.friends_enabled:
            raise AuthError(ErrorCode.FEATURE_DISABLED)
        return policy

    async def _pair(
        self, db: AsyncSession, actor: UUID, target: UUID, *, check_block: bool = True
    ) -> tuple[User, User]:
        if actor == target:
            raise AuthError(ErrorCode.USER_NOT_FOUND)
        rows = list(
            await db.scalars(
                select(User)
                .where(User.id.in_([actor, target]))
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        users = {user.id: user for user in rows}
        caller = users.get(actor)
        if caller is None:
            raise AuthError(ErrorCode.TOKEN_INVALID)
        if not caller.is_active:
            raise AuthError(ErrorCode.ACCOUNT_DISABLED)
        if caller.must_change_password:
            raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
        other = users.get(target)
        if (
            other is None
            or not other.is_active
            or (check_block and await db.scalar(select(blocked_between(actor, target))))
        ):
            raise AuthError(ErrorCode.USER_NOT_FOUND)
        return caller, other

    async def _capacity(
        self, db: AsyncSession, first: UUID, second: UUID, policy: SettingsSchema
    ) -> None:
        for user_id in (first, second):
            count = await db.scalar(
                select(func.count())
                .select_from(Friendship)
                .where(or_(Friendship.user_a_id == user_id, Friendship.user_b_id == user_id))
            )
            if count >= policy.max_friends_per_user:
                raise AuthError(ErrorCode.FRIEND_LIMIT_REACHED)

    async def search(self, db: AsyncSession, actor: UUID, email: str) -> list[SearchUser]:
        policy = await self._policy(db, actor)
        if not policy.friend_search_enabled:
            raise AuthError(ErrorCode.FEATURE_DISABLED)
        user = await db.scalar(
            select(User).where(
                func.lower(User.email) == email,
                User.id != actor,
                User.is_active.is_(True),
                User.discoverable_by_email.is_(True),
                ~blocked_between(actor, User.id),
            )
        )
        if user is None:
            return []
        pair = canonical_pair(actor, user.id)
        relationship = "none"
        if await db.get(Friendship, pair):
            relationship = "friend"
        else:
            cutoff = datetime.now(UTC) - timedelta(days=policy.friend_request_ttl_days)
            request = await db.scalar(
                select(FriendRequest)
                .where(
                    or_(
                        and_(
                            FriendRequest.from_user_id == actor,
                            FriendRequest.to_user_id == user.id,
                            FriendRequest.id.in_(latest_sent(actor)),
                            FriendRequest.status.in_(["pending", "declined"]),
                        ),
                        and_(
                            FriendRequest.from_user_id == user.id,
                            FriendRequest.to_user_id == actor,
                            FriendRequest.status == "pending",
                        ),
                    ),
                    FriendRequest.created_at >= cutoff,
                )
                .order_by(FriendRequest.created_at.desc())
                .limit(1)
            )
            if request:
                relationship = (
                    "request_sent" if request.from_user_id == actor else "request_received"
                )
        return [SearchUser(**PublicUser.from_user(user).model_dump(), relationship=relationship)]

    async def send(self, db: AsyncSession, actor: UUID, target: UUID) -> RequestItem:
        policy = await self._policy(db, actor)
        sender, recipient = await self._pair(db, actor, target)
        pair = canonical_pair(actor, target)
        if await db.get(Friendship, pair):
            raise AuthError(ErrorCode.ALREADY_FRIENDS)
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=policy.friend_request_ttl_days)
        between = or_(
            and_(FriendRequest.from_user_id == actor, FriendRequest.to_user_id == target),
            and_(FriendRequest.from_user_id == target, FriendRequest.to_user_id == actor),
        )
        await db.execute(
            update(FriendRequest)
            .where(between, FriendRequest.status == "pending", FriendRequest.created_at < cutoff)
            .values(status="expired")
        )
        requests = list(
            await db.scalars(
                select(FriendRequest).where(between, FriendRequest.status == "pending")
            )
        )
        if any(request.from_user_id == actor for request in requests):
            raise AuthError(ErrorCode.REQUEST_ALREADY_SENT)
        await self._capacity(db, actor, target, policy)
        if requests:  # Lời mời đến cho phép đồng ý ngay cả khi có cooldown cũ.
            request = requests[0]
            await self._establish(db, request, pair)
            await db.commit()
            await self.events.friendship_added(actor, target)
            return request_item(request, recipient, sender)
        declined_at = await db.scalar(
            select(func.max(FriendRequest.responded_at)).where(
                FriendRequest.from_user_id == actor,
                FriendRequest.to_user_id == target,
                FriendRequest.status.in_(["declined", "cancelled", "expired"]),
            )
        )
        if declined_at and declined_at + timedelta(hours=24) > now:
            raise AuthError(
                ErrorCode.REQUEST_COOLDOWN,
                retry_after=ceil((declined_at + timedelta(hours=24) - now).total_seconds()),
            )
        pending = await db.scalar(
            select(func.count())
            .select_from(FriendRequest)
            .where(
                FriendRequest.id.in_(latest_sent(actor)),
                FriendRequest.to_user_id != target,
                FriendRequest.status.in_(["pending", "declined"]),
                FriendRequest.created_at >= cutoff,
            )
        )
        if pending >= policy.max_pending_friend_requests:
            raise AuthError(ErrorCode.FRIEND_LIMIT_REACHED)
        request = FriendRequest(from_user_id=actor, to_user_id=target)
        db.add(request)
        await db.commit()
        result = request_item(request, sender, recipient)
        await self.events.request_received(target, result)
        return result

    async def requests(self, db: AsyncSession, actor: UUID, direction: str) -> list[RequestItem]:
        policy = await self._policy(db, actor)
        sender, recipient = aliased(User), aliased(User)
        query = (
            select(FriendRequest, sender, recipient)
            .join(sender, sender.id == FriendRequest.from_user_id)
            .join(recipient, recipient.id == FriendRequest.to_user_id)
            .where(
                FriendRequest.created_at
                >= datetime.now(UTC) - timedelta(days=policy.friend_request_ttl_days),
                sender.is_active.is_(True),
                recipient.is_active.is_(True),
                ~blocked_between(FriendRequest.from_user_id, FriendRequest.to_user_id),
            )
        )
        if direction == "incoming":
            query = query.where(
                FriendRequest.to_user_id == actor, FriendRequest.status == "pending"
            )
        else:
            query = query.where(
                FriendRequest.id.in_(latest_sent(actor)),
                FriendRequest.status.in_(["pending", "declined"]),
            )
        rows = await db.execute(query.order_by(FriendRequest.created_at.desc(), FriendRequest.id))
        return [request_item(request, sender, recipient) for request, sender, recipient in rows]

    async def _owned_request(
        self,
        db: AsyncSession,
        actor: UUID,
        request_id: UUID,
        policy: SettingsSchema,
        *,
        outgoing: bool = False,
    ) -> tuple[FriendRequest, User, User]:
        request = await db.get(FriendRequest, request_id)
        side = "from_user_id" if outgoing else "to_user_id"
        if request is None or getattr(request, side) != actor:
            raise AuthError(ErrorCode.REQUEST_NOT_FOUND)
        other = request.to_user_id if outgoing else request.from_user_id
        try:
            caller, target = await self._pair(db, actor, other)
        except AuthError as exc:
            if exc.code == ErrorCode.USER_NOT_FOUND:
                raise AuthError(ErrorCode.REQUEST_NOT_FOUND) from None
            raise
        await db.refresh(request)
        statuses = {"pending", "declined"} if outgoing else {"pending"}
        if request.status not in statuses or request.created_at < datetime.now(UTC) - timedelta(
            days=policy.friend_request_ttl_days
        ):
            raise AuthError(ErrorCode.REQUEST_NOT_FOUND)
        return request, caller, target

    async def _establish(
        self, db: AsyncSession, request: FriendRequest, pair: tuple[UUID, UUID]
    ) -> Friendship:
        friendship = Friendship(user_a_id=pair[0], user_b_id=pair[1])
        db.add(friendship)
        request.status, request.responded_at = "accepted", datetime.now(UTC)
        # Dừng hiển thị các lời mời cũ từng bị từ chối sau khi hai bên đã kết bạn.
        await db.execute(
            update(FriendRequest)
            .where(
                FriendRequest.from_user_id.in_(pair),
                FriendRequest.to_user_id.in_(pair),
                FriendRequest.status == "declined",
            )
            .values(status="expired")
        )
        return friendship

    async def accept(self, db: AsyncSession, actor: UUID, request_id: UUID) -> FriendItem:
        policy = await self._policy(db, actor)
        request, caller, other = await self._owned_request(db, actor, request_id, policy)
        pair = canonical_pair(actor, other.id)
        await self._capacity(db, actor, other.id, policy)
        friendship = await self._establish(db, request, pair)
        await db.commit()
        await self.events.friendship_added(actor, other.id)
        return self.item(other, friendship.created_at)

    async def dismiss(
        self, db: AsyncSession, actor: UUID, request_id: UUID, *, cancel: bool = False
    ) -> None:
        policy = await self._policy(db, actor, enabled=False)
        request, _, _ = await self._owned_request(db, actor, request_id, policy, outgoing=cancel)
        request.status = "cancelled" if cancel else "declined"
        if not cancel:
            request.responded_at = datetime.now(UTC)
        # Hủy lời mời đã bị từ chối vẫn giữ responded_at để không vượt cooldown.
        await db.commit()

    def item(self, user: User, since: datetime) -> FriendItem:
        return FriendItem(
            **PublicUser.from_user(user).model_dump(),
            since=since,
            is_online=self.events.is_online(user.id) if user.show_online_status else None,
        )

    async def friends(
        self, db: AsyncSession, actor: UUID, *, q: str | None, page: int, page_size: int
    ) -> FriendPage:
        await self._policy(db, actor)
        query = friend_users(actor)
        if q:
            query = query.where(User.display_name.icontains(q, autoescape=True))
        rows = await db.execute(query)
        items = [self.item(user, since) for user, since in rows]
        items.sort(
            key=lambda item: (item.is_online is not True, item.display_name.casefold(), item.id)
        )
        return FriendPage(
            items=items[(page - 1) * page_size : page * page_size],
            total=len(items),
            page=page,
            page_size=page_size,
        )

    async def remove(self, db: AsyncSession, actor: UUID, target: UUID) -> None:
        await self._policy(db, actor, enabled=False)
        await self._pair(db, actor, target)
        pair = canonical_pair(actor, target)
        result = await db.execute(
            delete(Friendship).where(
                Friendship.user_a_id == pair[0], Friendship.user_b_id == pair[1]
            )
        )
        if not result.rowcount:
            raise AuthError(ErrorCode.NOT_FRIENDS)
        invites = await self._cancel_call_invites(db, actor, target)
        await db.commit()
        await self.events.friendship_removed(actor, target, notify=target)
        await self.events.call_invites_cancelled(invites)

    async def blocks(self, db: AsyncSession, actor: UUID) -> list[BlockItem]:
        await self._policy(db, actor, enabled=False)
        rows = await db.execute(
            select(User, UserBlock.created_at)
            .join(UserBlock, User.id == UserBlock.blocked_id)
            .where(UserBlock.blocker_id == actor)
            .order_by(UserBlock.created_at.desc())
        )
        return [
            BlockItem(user=PublicUser.from_user(user), created_at=created_at)
            for user, created_at in rows
        ]

    async def block(self, db: AsyncSession, actor: UUID, target: UUID) -> BlockItem:
        await self._policy(db, actor, enabled=False)
        _, other = await self._pair(db, actor, target, check_block=False)
        pair = canonical_pair(actor, target)
        block = await db.get(UserBlock, (actor, target))
        if block is None:
            block = UserBlock(blocker_id=actor, blocked_id=target)
            db.add(block)
        await db.execute(
            delete(Friendship).where(
                Friendship.user_a_id == pair[0], Friendship.user_b_id == pair[1]
            )
        )
        await db.execute(
            update(FriendRequest)
            .where(
                or_(
                    and_(FriendRequest.from_user_id == actor, FriendRequest.to_user_id == target),
                    and_(FriendRequest.from_user_id == target, FriendRequest.to_user_id == actor),
                ),
                FriendRequest.status.in_(["pending", "declined"]),
            )
            .values(status="cancelled")
        )
        invites = await self._cancel_call_invites(db, actor, target)
        await db.commit()
        await self.events.friendship_removed(actor, target, notify=None)
        await self.events.call_invites_cancelled(invites)
        return BlockItem(user=PublicUser.from_user(other), created_at=block.created_at)

    async def unblock(self, db: AsyncSession, actor: UUID, target: UUID) -> None:
        await self._policy(db, actor, enabled=False)
        # Cùng thứ tự khóa với block; vẫn bỏ chặn được tài khoản đã bị vô hiệu hóa.
        await db.execute(
            select(User.id).where(User.id.in_([actor, target])).order_by(User.id).with_for_update()
        )
        result = await db.execute(
            delete(UserBlock).where(UserBlock.blocker_id == actor, UserBlock.blocked_id == target)
        )
        if not result.rowcount:
            raise AuthError(ErrorCode.USER_NOT_FOUND)
        await db.commit()

    async def expire_requests(self, db: AsyncSession) -> None:
        policy = await self.settings.get(db)
        await db.execute(
            update(FriendRequest)
            .where(
                FriendRequest.status == "pending",
                FriendRequest.created_at
                < datetime.now(UTC) - timedelta(days=policy.friend_request_ttl_days),
            )
            .values(status="expired")
        )
        await db.commit()
