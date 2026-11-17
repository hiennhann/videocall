import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.core.security import (
    Identity,
    hash_password,
    hash_refresh_token,
    issue_access_token,
    new_refresh_token,
    verify_password,
)
from app.models import DeviceTransfer, RefreshToken, User
from app.schemas.settings import SettingsSchema
from app.services.account_events import AccountEvents
from app.services.audit_service import AuditActor, record_audit
from app.services.login_attempts import LoginAttempts
from app.services.settings_service import SettingsService

REFRESH_GRACE = timedelta(seconds=10)
DEVICE_TRANSFER_TTL = timedelta(minutes=2)
logger = logging.getLogger(__name__)


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
    def __init__(
        self,
        secret: str,
        dummy_password_hash: str,
        settings: SettingsService,
        events: AccountEvents,
    ) -> None:
        self.secret = secret
        self.settings = settings
        self.events = events
        self._dummy_password_hash = dummy_password_hash
        self._login_attempts = LoginAttempts()

    async def register(
        self, db: AsyncSession, email: str, display_name: str, password: str
    ) -> User:
        if not (await self.settings.get(db)).allow_registration:
            raise AuthError(ErrorCode.REGISTRATION_DISABLED)
        return await self.create_account(db, email, display_name, password, role="user")

    async def create_account(
        self, db: AsyncSession, email: str, display_name: str, password: str, *, role: str
    ) -> User:
        self._check_password_length(
            password, (await self.settings.get(db)).password_min_length, "password"
        )
        user = User(
            email=email,
            display_name=display_name,
            role=role,
            password_hash=await hash_password(password),
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
        self,
        db: AsyncSession,
        email: str,
        password: str,
        client: ClientInfo,
        *,
        admin_only: bool = False,
        use_cookie: bool = False,
    ) -> tuple[User, SessionTokens]:
        policy = await self.settings.get(db)
        ip = client.login_ip
        self._check_login_lock(email, ip)
        user = await db.scalar(
            select(User).where(func.lower(User.email) == email).with_for_update()
        )
        self._check_login_lock(email, ip)
        stored_hash = user.password_hash if user is not None else self._dummy_password_hash
        valid = await verify_password(password, stored_hash)
        if not valid or user is None:
            remaining = self._login_attempts.record_failure(
                email, ip, policy.login_max_attempts, policy.login_lockout_minutes * 60
            )
            if remaining is not None:
                raise AuthError(ErrorCode.LOGIN_LOCKED, retry_after=remaining)
            raise AuthError(ErrorCode.INVALID_CREDENTIALS)

        if not user.is_active:
            raise AuthError(ErrorCode.ACCOUNT_DISABLED)
        if admin_only and user.role != "admin":
            raise AuthError(ErrorCode.FORBIDDEN)
        now = datetime.now(UTC)
        if not admin_only:
            family = await self._active_family(db, user.id, now)
            if family is not None:
                raw = new_refresh_token()
                pending = await db.get(DeviceTransfer, user.id) or DeviceTransfer(user_id=user.id)
                pending.token_hash = hash_refresh_token(raw)
                pending.expected_family = family
                pending.use_cookie = use_cookie
                pending.expires_at = now + DEVICE_TRANSFER_TTL
                db.add(pending)
                expires_at = pending.expires_at.isoformat()
                await db.commit()
                self._login_attempts.reset(email, ip)
                raise AuthError(
                    ErrorCode.DEVICE_TRANSFER_REQUIRED,
                    details={"transfer_token": raw, "expires_at": expires_at},
                )
        user.last_login_at = now
        _, tokens = self._new_session(
            db, user, uuid4(), now, client, policy, scope="admin" if admin_only else "user"
        )
        if admin_only:
            record_audit(
                db, AuditActor(user.id, user.email, client.ip), "admin.login", "user", str(user.id)
            )
        await db.commit()
        self._login_attempts.reset(email, ip)
        return user, tokens

    async def confirm_device_transfer(
        self, db: AsyncSession, raw: str, client: ClientInfo, *, use_cookie: bool
    ) -> tuple[User, SessionTokens]:
        policy = await self.settings.get(db)
        token_hash = hash_refresh_token(raw)
        user = await self._lock_transfer_owner(db, token_hash)
        if user is None:
            raise AuthError(ErrorCode.DEVICE_TRANSFER_INVALID)
        pending = await db.get(DeviceTransfer, user.id)
        now = datetime.now(UTC)
        if (
            pending is None
            or pending.token_hash != token_hash
            or pending.use_cookie != use_cookie
            or pending.expires_at <= now
            or not user.is_active
            or await self._active_family(db, user.id, now) != pending.expected_family
        ):
            raise AuthError(ErrorCode.DEVICE_TRANSFER_INVALID)
        previous_family = pending.expected_family
        await self.revoke_sessions(db, user.id, now, only_family=previous_family)
        await db.delete(pending)
        user.last_login_at = now
        _, tokens = self._new_session(db, user, uuid4(), now, client, policy, scope="user")
        await db.commit()
        await self.events.sessions_revoked(
            user.id, "DEVICE_SESSION_REPLACED", only_family=previous_family
        )
        return user, tokens

    async def cancel_device_transfer(self, db: AsyncSession, raw: str) -> None:
        token_hash = hash_refresh_token(raw)
        if await self._lock_transfer_owner(db, token_hash) is not None:
            await db.execute(delete(DeviceTransfer).where(DeviceTransfer.token_hash == token_hash))
            await db.commit()

    async def _lock_transfer_owner(self, db: AsyncSession, token_hash: str) -> User | None:
        user_id = await db.scalar(
            select(DeviceTransfer.user_id).where(DeviceTransfer.token_hash == token_hash)
        )
        return await self.lock_user(db, user_id) if user_id is not None else None

    async def refresh(
        self, db: AsyncSession, raw_token: str, client: ClientInfo, *, admin_only: bool = False
    ) -> SessionTokens:
        policy = await self.settings.get(db)
        token_hash = hash_refresh_token(raw_token)
        user = await self._lock_token_owner(db, token_hash)
        if user is None:
            raise AuthError(ErrorCode.INVALID_REFRESH_TOKEN)

        token = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        now = datetime.now(UTC)
        scope = "admin" if admin_only else "user"
        if token is None or token.expires_at <= now or token.scope != scope:
            raise AuthError(ErrorCode.INVALID_REFRESH_TOKEN)
        if not user.is_active:
            raise AuthError(ErrorCode.ACCOUNT_DISABLED)
        if admin_only and user.role != "admin":
            raise AuthError(ErrorCode.FORBIDDEN)

        if token.revoked_at is not None:
            if token.replaced_by_id is not None and now - token.revoked_at > REFRESH_GRACE:
                await self.revoke_sessions(db, user.id, now, only_family=token.family_id)
                await db.commit()
                await self.events.sessions_revoked(
                    user.id, "SESSIONS_REVOKED", only_family=token.family_id
                )
                logger.warning("Refresh token bị dùng lại, đã thu hồi phiên.")
            raise AuthError(ErrorCode.INVALID_REFRESH_TOKEN)

        if user.must_change_password:
            raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
        replacement, tokens = self._new_session(
            db, user, token.family_id, now, client, policy, scope=scope
        )
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
                await self.revoke_sessions(db, user.id, datetime.now(UTC), only_family=family)
                await db.commit()
                await self.events.sessions_revoked(user.id, "SESSIONS_REVOKED", only_family=family)

    async def logout_all(self, db: AsyncSession, user_id: UUID) -> None:
        await self.lock_user(db, user_id)
        await self.revoke_sessions(db, user_id, datetime.now(UTC))
        await db.commit()
        await self.events.sessions_revoked(user_id, "SESSIONS_REVOKED")

    async def guest(self, db: AsyncSession, display_name: str) -> tuple[Identity, str, int]:
        policy = await self.settings.get(db)
        if policy.maintenance_mode:
            raise AuthError(ErrorCode.MAINTENANCE_MODE)
        if not policy.allow_guest:
            raise AuthError(ErrorCode.GUEST_DISABLED)

        identity = Identity(uuid4(), display_name)
        token, ttl = issue_access_token(
            identity, self.secret, datetime.now(UTC), policy.guest_ttl_minutes * 60
        )
        return identity, token, ttl

    async def change_password(
        self, db: AsyncSession, user_id: UUID, family_id: UUID, current: str, new: str
    ) -> None:
        policy = await self.settings.get(db)
        user = await self.lock_user(db, user_id)
        if user is None:
            raise AuthError(ErrorCode.TOKEN_INVALID)
        if not user.is_active:
            raise AuthError(ErrorCode.ACCOUNT_DISABLED)
        if not await verify_password(current, user.password_hash):
            raise AuthError(ErrorCode.WRONG_PASSWORD)
        if current == new:
            raise AuthError(ErrorCode.PASSWORD_UNCHANGED)

        self._check_password_length(new, policy.password_min_length, "new_password")
        user.password_hash = await hash_password(new)
        user.must_change_password = False
        await db.execute(delete(DeviceTransfer).where(DeviceTransfer.user_id == user_id))
        await self.revoke_sessions(db, user_id, datetime.now(UTC), keep_family=family_id)
        await db.commit()
        await self.events.sessions_revoked(user_id, "SESSIONS_REVOKED", keep_family=family_id)

    @staticmethod
    def _check_password_length(password: str, minimum: int, field: str) -> None:
        if len(password) < minimum:
            raise AuthError(
                ErrorCode.VALIDATION_ERROR, fields={field: f"Tối thiểu {minimum} ký tự."}
            )

    def _check_login_lock(self, email: str, ip: str) -> None:
        remaining = self._login_attempts.retry_after(email, ip)
        if remaining is not None:
            raise AuthError(ErrorCode.LOGIN_LOCKED, retry_after=remaining)

    @staticmethod
    def _active_tokens(user_id: UUID, now: datetime, scope: str):
        return select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.scope == scope,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )

    @classmethod
    async def _active_family(cls, db: AsyncSession, user_id: UUID, now: datetime) -> UUID | None:
        return await db.scalar(
            cls._active_tokens(user_id, now, "user")
            .with_only_columns(RefreshToken.family_id)
            .limit(1)
        )

    @classmethod
    async def has_active_session(
        cls, db: AsyncSession, user_id: UUID, family_id: UUID, *, scope: str = "user"
    ) -> bool:
        session_id = await db.scalar(
            cls._active_tokens(user_id, datetime.now(UTC), scope)
            .with_only_columns(RefreshToken.id)
            .where(RefreshToken.family_id == family_id)
            .limit(1)
        )
        return session_id is not None

    def _new_session(
        self,
        db: AsyncSession,
        user: User,
        family: UUID,
        now: datetime,
        client: ClientInfo,
        policy: SettingsSchema,
        *,
        scope: str,
    ) -> tuple[RefreshToken, SessionTokens]:
        raw_token = new_refresh_token()
        refresh = RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            family_id=family,
            scope=scope,
            expires_at=now + timedelta(days=policy.refresh_token_ttl_days),
            created_at=now,
            ip=client.ip,
            user_agent=client.user_agent,
        )
        db.add(refresh)
        token, ttl = issue_access_token(
            Identity(user.id, user.display_name, family, user.role),
            self.secret,
            now,
            policy.access_token_ttl_minutes * 60,
        )
        return refresh, SessionTokens(token, raw_token, ttl)

    async def _lock_token_owner(self, db: AsyncSession, token_hash: str) -> User | None:
        user_id = await db.scalar(
            select(RefreshToken.user_id).where(RefreshToken.token_hash == token_hash)
        )
        return await self.lock_user(db, user_id) if user_id is not None else None

    @staticmethod
    async def lock_user(db: AsyncSession, user_id: UUID) -> User | None:
        # Dùng cùng một khóa cho mọi thao tác có thể cấp hoặc thu hồi phiên của người dùng.
        return await db.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def revoke_sessions(
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
