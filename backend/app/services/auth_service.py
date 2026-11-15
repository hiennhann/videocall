import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.core.security import (
    REFRESH_TTL_DAYS,
    Identity,
    hash_password,
    hash_refresh_token,
    issue_access_token,
    new_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User
from app.services.login_attempts import LoginAttempts

REFRESH_GRACE = timedelta(seconds=10)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuthPolicy:
    allow_registration: bool = True
    allow_guest: bool = True
    maintenance_mode: bool = False


@dataclass(frozen=True, slots=True)
class ClientInfo:
    ip: IPv4Address | IPv6Address | None
    user_agent: str | None

    @property
    def login_ip(self) -> str:
        return str(self.ip) if self.ip is not None else "unknown"


@dataclass(frozen=True, slots=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(self, secret: str, dummy_password_hash: str) -> None:
        self.secret = secret
        self.policy = AuthPolicy()
        self._dummy_password_hash = dummy_password_hash
        self._login_attempts = LoginAttempts()

    async def register(
        self, db: AsyncSession, email: str, display_name: str, password: str
    ) -> User:
        if not self.policy.allow_registration:
            raise AuthError(ErrorCode.REGISTRATION_DISABLED)

        user = User(
            email=email, display_name=display_name, password_hash=await hash_password(password)
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise AuthError(ErrorCode.EMAIL_TAKEN) from None
            raise
        return user

    async def login(
        self, db: AsyncSession, email: str, password: str, client: ClientInfo
    ) -> tuple[User, SessionTokens]:
        ip = client.login_ip
        self._check_login_lock(email, ip)
        user = await db.scalar(
            select(User).where(func.lower(User.email) == email).with_for_update()
        )
        self._check_login_lock(email, ip)
        stored_hash = user.password_hash if user is not None else self._dummy_password_hash
        valid = await verify_password(password, stored_hash)
        if not valid or user is None:
            remaining = self._login_attempts.record_failure(email, ip)
            if remaining is not None:
                raise AuthError(ErrorCode.LOGIN_LOCKED, retry_after=remaining)
            raise AuthError(ErrorCode.INVALID_CREDENTIALS)

        _, tokens = self._new_session(db, user, uuid4(), datetime.now(UTC), client)
        await db.commit()
        self._login_attempts.reset(email, ip)
        return user, tokens

    async def refresh(self, db: AsyncSession, raw_token: str, client: ClientInfo) -> SessionTokens:
        token_hash = hash_refresh_token(raw_token)
        user = await self._lock_token_owner(db, token_hash)
        if user is None:
            raise AuthError(ErrorCode.INVALID_REFRESH_TOKEN)

        token = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        now = datetime.now(UTC)
        if token is None or token.expires_at <= now:
            raise AuthError(ErrorCode.INVALID_REFRESH_TOKEN)

        if token.revoked_at is not None:
            if token.replaced_by_id is not None and now - token.revoked_at > REFRESH_GRACE:
                await self._revoke_sessions(db, user.id, now, only_family=token.family_id)
                await db.commit()
                logger.warning("Refresh token bị dùng lại, đã thu hồi phiên.")
            raise AuthError(ErrorCode.INVALID_REFRESH_TOKEN)

        replacement, tokens = self._new_session(db, user, token.family_id, now, client)
        await db.flush()
        token.revoked_at = now
        token.replaced_by_id = replacement.id
        await db.commit()
        return tokens

    async def logout(self, db: AsyncSession, raw_token: str) -> None:
        token_hash = hash_refresh_token(raw_token)
        user = await self._lock_token_owner(db, token_hash)
        if user is not None:
            family = await db.scalar(
                select(RefreshToken.family_id).where(RefreshToken.token_hash == token_hash)
            )
            if family is not None:
                await self._revoke_sessions(db, user.id, datetime.now(UTC), only_family=family)
                await db.commit()

    async def logout_all(self, db: AsyncSession, user_id: UUID) -> None:
        await self._lock_user(db, user_id)
        await self._revoke_sessions(db, user_id, datetime.now(UTC))
        await db.commit()

    def guest(self, display_name: str) -> tuple[Identity, str, int]:
        if self.policy.maintenance_mode:
            raise AuthError(ErrorCode.MAINTENANCE_MODE)
        if not self.policy.allow_guest:
            raise AuthError(ErrorCode.GUEST_DISABLED)

        identity = Identity(uuid4(), display_name)
        token, ttl = issue_access_token(identity, self.secret, datetime.now(UTC))
        return identity, token, ttl

    async def change_password(
        self, db: AsyncSession, user_id: UUID, family_id: UUID, current: str, new: str
    ) -> None:
        user = await self._lock_user(db, user_id)
        if user is None:
            raise AuthError(ErrorCode.TOKEN_INVALID)
        if not await verify_password(current, user.password_hash):
            raise AuthError(ErrorCode.WRONG_PASSWORD)
        if current == new:
            raise AuthError(ErrorCode.PASSWORD_UNCHANGED)

        user.password_hash = await hash_password(new)
        await self._revoke_sessions(db, user_id, datetime.now(UTC), keep_family=family_id)
        await db.commit()

    def _check_login_lock(self, email: str, ip: str) -> None:
        remaining = self._login_attempts.retry_after(email, ip)
        if remaining is not None:
            raise AuthError(ErrorCode.LOGIN_LOCKED, retry_after=remaining)

    def _new_session(
        self, db: AsyncSession, user: User, family: UUID, now: datetime, client: ClientInfo
    ) -> tuple[RefreshToken, SessionTokens]:
        raw_token = new_refresh_token()
        refresh = RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            family_id=family,
            expires_at=now + timedelta(days=REFRESH_TTL_DAYS),
            created_at=now,
            ip=client.ip,
            user_agent=client.user_agent,
        )
        db.add(refresh)
        token, ttl = issue_access_token(
            Identity(user.id, user.display_name, family), self.secret, now
        )
        return refresh, SessionTokens(token, raw_token, ttl)

    async def _lock_token_owner(self, db: AsyncSession, token_hash: str) -> User | None:
        user_id = await db.scalar(
            select(RefreshToken.user_id).where(RefreshToken.token_hash == token_hash)
        )
        return await self._lock_user(db, user_id) if user_id is not None else None

    @staticmethod
    async def _lock_user(db: AsyncSession, user_id: UUID) -> User | None:
        # Dùng cùng một khóa cho mọi thao tác có thể cấp hoặc thu hồi phiên của người dùng.
        return await db.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def _revoke_sessions(
        db: AsyncSession,
        user_id: UUID,
        now: datetime,
        *,
        only_family: UUID | None = None,
        keep_family: UUID | None = None,
    ) -> None:
        statement = update(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        if only_family is not None:
            statement = statement.where(RefreshToken.family_id == only_family)
        if keep_family is not None:
            statement = statement.where(RefreshToken.family_id != keep_family)
        await db.execute(statement.values(revoked_at=now))
