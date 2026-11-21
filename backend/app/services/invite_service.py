from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.models import Room, RoomInvite, User
from app.schemas.friends import PublicUser
from app.services.friend_service import are_friends, blocked_between
from app.services.user_service import editable_user


class InviteService:
    def __init__(self, state, settings, notify, metrics) -> None:
        self.state, self.settings, self.notify, self.metrics = state, settings, notify, metrics

    @staticmethod
    def payload(invite: RoomInvite, room: Room, sender: User | None) -> dict:
        return {
            "id": str(invite.id),
            "room": {
                "code": room.code,
                "name": room.name,
                "mode": room.mode,
                "has_password": room.is_private,
            },
            "from": PublicUser.from_user(sender).model_dump(mode="json") if sender else None,
            "expires_at": invite.expires_at.isoformat(),
        }

    async def send(self, db: AsyncSession, actor: UUID, code: str, targets: list[UUID]) -> dict:
        policy = await self.settings.get(db)
        if not policy.friends_enabled:
            raise AuthError(ErrorCode.FEATURE_DISABLED)
        presence = self.state.get_room(code)
        if presence is None:
            if not await db.scalar(select(Room.id).where(Room.code == code)):
                raise AuthError(ErrorCode.ROOM_NOT_FOUND)
            raise AuthError(ErrorCode.NOT_IN_ROOM)
        async with presence.lock:
            users = {
                user.id: user
                for user in await db.scalars(
                    select(User)
                    .where(User.id.in_([actor, *targets]))
                    .order_by(User.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            }
            sender = await editable_user(db, actor)
            room = await db.scalar(select(Room).where(Room.code == code).with_for_update())
            if room is None:
                raise AuthError(ErrorCode.ROOM_NOT_FOUND)
            if room.status != "active":
                raise AuthError(ErrorCode.ROOM_CLOSED)
            members = {peer.user_id for peer in presence.peers.values()}
            if str(actor) not in members:
                raise AuthError(ErrorCode.NOT_IN_ROOM)
            now = datetime.now(UTC)
            expired = await self.transition(
                db, "expired", RoomInvite.room_id == room.id, RoomInvite.expires_at <= now
            )
            pending = set(
                await db.scalars(
                    select(RoomInvite.invitee_id).where(
                        RoomInvite.room_id == room.id, RoomInvite.status == "pending"
                    )
                )
            )
            sent, skipped, notifications = [], [], []
            for target in dict.fromkeys(targets):
                user = users.get(target)
                if (
                    target == actor
                    or user is None
                    or not user.is_active
                    or user.must_change_password
                ):
                    reason = "not_allowed"
                elif not await are_friends(db, actor, target):
                    reason = "not_friend"
                elif str(target) in members:
                    reason = "already_in_room"
                elif target in pending:
                    reason = "already_invited"
                elif len(pending) >= policy.max_invites_per_call:
                    reason = "limit_reached"
                else:
                    invite = RoomInvite(
                        room_id=room.id,
                        inviter_id=actor,
                        invitee_id=target,
                        expires_at=now + timedelta(seconds=policy.invite_ttl_seconds),
                    )
                    db.add(invite)
                    await db.flush()
                    pending.add(target)
                    sent.append({"user_id": target, "invite_id": invite.id})
                    notifications.append((target, self.payload(invite, room, sender)))
                    continue
                skipped.append({"user_id": target, "reason": reason})
            await db.commit()
            self.metrics.call_invites.labels("pending").inc(len(sent))
            await self.cancelled(expired, "expired")
            for target, payload in notifications:
                await self.notify("call_invite", {"invite": payload}, target)
            return {"sent": sent, "skipped": skipped}

    async def inbox(self, db: AsyncSession, actor: UUID) -> list[dict]:
        await editable_user(db, actor)
        rows = await db.execute(
            select(RoomInvite, Room, User)
            .join(Room, Room.id == RoomInvite.room_id)
            .join(User, User.id == RoomInvite.inviter_id)
            .where(
                RoomInvite.invitee_id == actor,
                RoomInvite.status == "pending",
                RoomInvite.expires_at > datetime.now(UTC),
                Room.status == "active",
                User.is_active.is_(True),
                ~blocked_between(actor, User.id),
            )
            .order_by(RoomInvite.created_at.desc())
        )
        return [self.payload(invite, room, user) for invite, room, user in rows]

    async def validate_join(
        self, db: AsyncSession, room: Room, actor: UUID | None, invite_id: UUID
    ) -> None:
        invite = await db.scalar(
            select(RoomInvite)
            .where(
                RoomInvite.id == invite_id,
                RoomInvite.room_id == room.id,
                RoomInvite.invitee_id == actor,
            )
            .with_for_update()
        )
        if invite and (
            invite.status == "expired"
            or (invite.status == "pending" and invite.expires_at <= datetime.now(UTC))
        ):
            raise AuthError(ErrorCode.INVITE_EXPIRED)
        if invite is None or invite.status != "pending" or invite.inviter_id is None:
            raise AuthError(ErrorCode.INVITE_INVALID)
        sender = await db.get(User, invite.inviter_id)
        if not sender or not sender.is_active or not await are_friends(db, sender.id, actor):
            raise AuthError(ErrorCode.INVITE_INVALID)

    async def joined(self, db: AsyncSession, room: Room, actor: UUID) -> None:
        rows = await self.transition(
            db,
            "accepted",
            RoomInvite.room_id == room.id,
            RoomInvite.invitee_id == actor,
            RoomInvite.expires_at > datetime.now(UTC),
        )
        await db.commit()
        for invite in rows:
            await self.responded(invite)

    async def responded(self, invite: RoomInvite) -> None:
        self.metrics.call_invites.labels(invite.status).inc()
        if invite.inviter_id is not None:
            await self.notify(
                "call_invite_responded",
                {
                    "invite_id": str(invite.id),
                    "status": invite.status,
                    "by_user_id": str(invite.invitee_id),
                },
                invite.inviter_id,
            )

    async def decline(self, db: AsyncSession, actor: UUID, invite_id: UUID) -> None:
        await editable_user(db, actor)
        invite = await db.scalar(
            select(RoomInvite)
            .where(RoomInvite.id == invite_id, RoomInvite.invitee_id == actor)
            .with_for_update()
        )
        if invite is None or invite.status not in {"pending", "expired"}:
            raise AuthError(ErrorCode.INVITE_NOT_FOUND)
        if invite.status == "expired" or invite.expires_at <= datetime.now(UTC):
            raise AuthError(ErrorCode.INVITE_EXPIRED)
        invite.status, invite.responded_at = "declined", datetime.now(UTC)
        await db.commit()
        await self.responded(invite)

    async def cancel(self, db: AsyncSession, actor: UUID, code: str, invite_id: UUID) -> None:
        await editable_user(db, actor)
        row = (
            await db.execute(
                select(RoomInvite, Room)
                .join(Room, Room.id == RoomInvite.room_id)
                .where(Room.code == code, RoomInvite.id == invite_id)
                .with_for_update(of=RoomInvite)
            )
        ).one_or_none()
        if row is None:
            raise AuthError(ErrorCode.INVITE_NOT_FOUND)
        invite, room = row
        presence = self.state.get_room(code)
        host = presence.host() if presence else None
        if (
            actor != invite.inviter_id
            and actor != room.host_id
            and not (host and host.user_id == str(actor))
        ):
            raise AuthError(ErrorCode.FORBIDDEN)
        rows = await self.transition(
            db, "cancelled", RoomInvite.id == invite.id, RoomInvite.expires_at > func.now()
        )
        if not rows:
            raise AuthError(ErrorCode.INVITE_NOT_FOUND)
        await db.commit()
        await self.cancelled(rows, "inviter_cancelled")

    @staticmethod
    async def transition(db: AsyncSession, status: str, *filters) -> list[RoomInvite]:
        requested_status = (
            case((RoomInvite.expires_at <= func.now(), "expired"), else_="cancelled")
            if status == "cancelled"
            else status
        )
        return list(
            await db.scalars(
                update(RoomInvite)
                .where(RoomInvite.status == "pending", *filters)
                .values(status=requested_status, responded_at=func.now())
                .returning(RoomInvite)
            )
        )

    async def cancelled(self, rows: list[RoomInvite], reason: str) -> None:
        for invite in rows:
            self.metrics.call_invites.labels(invite.status).inc()
            await self.notify(
                "call_invite_cancelled",
                {
                    "invite_id": str(invite.id),
                    "reason": "expired" if invite.status == "expired" else reason,
                },
                invite.invitee_id,
            )

    async def sweep(self, db: AsyncSession) -> None:
        expired = await self.transition(db, "expired", RoomInvite.expires_at <= datetime.now(UTC))
        closed = await self.transition(
            db, "cancelled", RoomInvite.room_id.in_(select(Room.id).where(Room.status == "closed"))
        )
        removed = await self.transition(
            db,
            "cancelled",
            or_(
                RoomInvite.inviter_id.is_(None),
                RoomInvite.inviter_id.in_(select(User.id).where(User.is_active.is_(False))),
                RoomInvite.invitee_id.in_(select(User.id).where(User.is_active.is_(False))),
            ),
        )
        await db.commit()
        await self.cancelled(expired, "expired")
        await self.cancelled(closed, "room_closed")
        await self.cancelled(removed, "account_unavailable")
