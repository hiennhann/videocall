from collections.abc import AsyncIterator
from dataclasses import dataclass
from ipaddress import ip_address
from math import ceil
from time import time
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from limits import parse
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.core.security import AccessToken, decode_access_token
from app.models import User
from app.services.audit_service import AuditActor
from app.services.auth_service import AuthService, ClientInfo
from app.services.settings_service import SettingsService
from app.services.user_service import get_user

bearer = HTTPBearer(auto_error=False)
ADMIN_LIMIT = parse("120/minute")


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as db:
        yield db


async def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


type DB = Annotated[AsyncSession, Depends(get_db)]
type Auth = Annotated[AuthService, Depends(get_auth_service)]


async def get_settings_service(request: Request) -> SettingsService:
    return request.app.state.settings_service


type OperationalSettings = Annotated[SettingsService, Depends(get_settings_service)]


def client_info(request: Request) -> ClientInfo:
    try:
        ip = ip_address(get_remote_address(request))
    except ValueError:
        ip = None
    user_agent = request.headers.get("user-agent")
    return ClientInfo(ip, user_agent.replace("\x00", "")[:255] if user_agent else None)


@dataclass(frozen=True, slots=True)
class Principal:
    access: AccessToken
    user: User | None


async def current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: Auth,
    db: DB,
) -> Principal:
    if credentials is None:
        raise AuthError(ErrorCode.UNAUTHENTICATED)
    access = decode_access_token(credentials.credentials, auth.secret)
    user = await get_user(db, access.identity.id) if access.identity.family_id is not None else None
    if user is not None and not user.is_active:
        raise AuthError(ErrorCode.ACCOUNT_DISABLED)
    return Principal(access, user)


type CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


@dataclass(frozen=True, slots=True)
class Member:
    user: User
    family_id: UUID


async def require_account(principal: CurrentPrincipal) -> Member:
    family_id = principal.access.identity.family_id
    if principal.user is None or family_id is None:
        raise AuthError(ErrorCode.GUEST_NOT_ALLOWED)
    return Member(principal.user, family_id)


type CurrentAccount = Annotated[Member, Depends(require_account)]


async def require_member(account: CurrentAccount) -> Member:
    if account.user.must_change_password:
        raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
    return account


type CurrentMember = Annotated[Member, Depends(require_member)]


async def require_admin(request: Request, principal: CurrentPrincipal) -> AuditActor:
    user = principal.user
    if user is None or user.role != "admin":
        raise AuthError(ErrorCode.FORBIDDEN)
    if user.must_change_password:
        raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)

    limiter = request.app.state.limiter.limiter
    key = str(user.id)
    if not limiter.hit(ADMIN_LIMIT, "admin", key):
        reset, _ = limiter.get_window_stats(ADMIN_LIMIT, "admin", key)
        raise AuthError(ErrorCode.RATE_LIMITED, retry_after=max(1, ceil(reset - time())))
    return AuditActor(user.id, user.email, client_info(request).ip)


type CurrentAdmin = Annotated[AuditActor, Depends(require_admin)]
