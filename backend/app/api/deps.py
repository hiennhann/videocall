from collections.abc import AsyncIterator
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.core.security import AccessToken, decode_access_token
from app.models import User
from app.services.auth_service import AuthService, ClientInfo
from app.services.user_service import get_user

bearer = HTTPBearer(auto_error=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as db:
        yield db


async def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


type DB = Annotated[AsyncSession, Depends(get_db)]
type Auth = Annotated[AuthService, Depends(get_auth_service)]


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
    return Principal(access, user)


type CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


@dataclass(frozen=True, slots=True)
class Member:
    user: User
    family_id: UUID


async def require_member(principal: CurrentPrincipal) -> Member:
    family_id = principal.access.identity.family_id
    if principal.user is None or family_id is None:
        raise AuthError(ErrorCode.GUEST_NOT_ALLOWED)
    return Member(principal.user, family_id)


type CurrentMember = Annotated[Member, Depends(require_member)]
