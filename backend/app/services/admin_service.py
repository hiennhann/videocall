import secrets
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.core.security import hash_password
from app.models import RefreshToken, User
from app.services.account_events import AccountEvents
from app.services.audit_service import AuditActor, record_audit
from app.services.auth_service import AuthService


async def list_users(
    db: AsyncSession,
    *,
    q: str | None,
    role: str | None,
    is_active: bool | None,
    page: int,
    page_size: int,
) -> tuple[list[User], int]:
    query = select(User)
    if q:
        query = query.where(
            or_(
                User.email.icontains(q, autoescape=True),
                User.display_name.icontains(q, autoescape=True),
            )
        )
    if role is not None:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.scalars(
        query.order_by(User.created_at.desc(), User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total or 0


async def get_admin_target(db: AsyncSession, user_id: UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise AuthError(ErrorCode.USER_NOT_FOUND)
    return user


async def count_user_sessions(db: AsyncSession, user_id: UUID) -> int:
    total = await db.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )
    return total or 0


async def user_counts(db: AsyncSession) -> tuple[int, list[tuple[date, int]]]:
    total = await db.scalar(select(func.count()).select_from(User))
    today = datetime.now(UTC).date()
    start = today - timedelta(days=6)
    day = func.date(func.timezone("UTC", User.created_at))
    rows = await db.execute(
        select(day, func.count())
        .where(User.created_at >= datetime.combine(start, datetime.min.time(), UTC))
        .group_by(day)
    )
    by_day = dict(rows.tuples().all())
    return total or 0, [
        (day, by_day.get(day, 0)) for day in (start + timedelta(days=i) for i in range(7))
    ]


class AdminService:
    def __init__(self, events: AccountEvents) -> None:
        self.events = events

    async def _locked_target(self, db: AsyncSession, actor: AuditActor, user_id: UUID) -> User:
        # Tuần tự hóa thay đổi quyền để hai admin không thể đồng thời bỏ quyền của nhau.
        await db.execute(select(func.pg_advisory_xact_lock(932155)))
        caller = await db.get(User, actor.id, populate_existing=True)
        if caller is None or not caller.is_active or caller.role != "admin":
            raise AuthError(ErrorCode.FORBIDDEN)
        if caller.must_change_password:
            raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
        user = await AuthService.lock_user(db, user_id)
        if user is None:
            raise AuthError(ErrorCode.USER_NOT_FOUND)
        return user

    async def _preserve_last_admin(self, db: AsyncSession, user: User) -> None:
        if user.role == "admin" and user.is_active:
            count = await db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "admin", User.is_active.is_(True))
            )
            if count == 1:
                raise AuthError(ErrorCode.LAST_ADMIN)

    async def patch_user(
        self, db: AsyncSession, actor: AuditActor, user_id: UUID, changes: dict[str, str | bool]
    ) -> User:
        user = await self._locked_target(db, actor, user_id)
        before = {key: getattr(user, key) for key in changes}
        role = changes.get("role", user.role)
        active = changes.get("is_active", user.is_active)
        if actor.id == user.id and (role != user.role or active != user.is_active):
            raise AuthError(ErrorCode.CANNOT_MODIFY_SELF)
        if role != "admin" or not active:
            await self._preserve_last_admin(db, user)
        was_active = user.is_active
        for key, value in changes.items():
            setattr(user, key, value)
        locked = was_active and not user.is_active
        if locked:
            await AuthService.revoke_sessions(db, user.id, datetime.now(UTC))
        action = (
            "user.lock"
            if locked
            else "user.unlock"
            if not was_active and user.is_active
            else "user.update"
        )
        record_audit(
            db, actor, action, "user", str(user.id), detail={"before": before, "after": changes}
        )
        await db.commit()
        if locked:
            await self.events.sessions_revoked(user.id, "ACCOUNT_DISABLED")
        return user

    async def reset_password(self, db: AsyncSession, actor: AuditActor, user_id: UUID) -> str:
        password = secrets.token_urlsafe(48)
        password_hash = await hash_password(password)
        user = await self._locked_target(db, actor, user_id)
        user.password_hash = password_hash
        user.must_change_password = True
        await AuthService.revoke_sessions(db, user.id, datetime.now(UTC))
        record_audit(db, actor, "user.reset_password", "user", str(user.id))
        await db.commit()
        await self.events.sessions_revoked(user.id, "SESSIONS_REVOKED")
        return password

    async def revoke_sessions(self, db: AsyncSession, actor: AuditActor, user_id: UUID) -> None:
        user = await self._locked_target(db, actor, user_id)
        await AuthService.revoke_sessions(db, user.id, datetime.now(UTC))
        record_audit(db, actor, "user.revoke_sessions", "user", str(user.id))
        await db.commit()
        await self.events.sessions_revoked(user.id, "SESSIONS_REVOKED")

    async def delete_user(self, db: AsyncSession, actor: AuditActor, user_id: UUID) -> None:
        if actor.id == user_id:
            raise AuthError(ErrorCode.CANNOT_MODIFY_SELF)
        user = await self._locked_target(db, actor, user_id)
        await self._preserve_last_admin(db, user)
        rooms = await self.events.close_owned_rooms(db, user_id, datetime.now(UTC))
        record_audit(db, actor, "user.delete", "user", str(user_id), detail={"email": user.email})
        await db.delete(user)
        await db.commit()
        await self.events.owned_rooms_closed(rooms)
        await self.events.sessions_revoked(user_id, "SESSIONS_REVOKED")
