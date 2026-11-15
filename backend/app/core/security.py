import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.errors import AuthError, ErrorCode

ACCESS_TTL = 15 * 60
GUEST_TTL = 120 * 60
REFRESH_TTL_DAYS = 7
password_hasher = PasswordHash.recommended()


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(password_hasher.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(password_hasher.verify, password, password_hash)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Identity:
    id: UUID
    display_name: str
    family_id: UUID | None = None

    @property
    def subject(self) -> str:
        return f"guest:{self.id}" if self.family_id is None else str(self.id)


@dataclass(frozen=True, slots=True)
class AccessToken:
    identity: Identity
    issued_at: datetime
    expires_at: datetime


def issue_access_token(identity: Identity, secret: str, now: datetime) -> tuple[str, int]:
    is_guest = identity.family_id is None
    ttl = GUEST_TTL if is_guest else ACCESS_TTL
    issued_at = int(now.timestamp())
    claims = {
        "iss": "videocall",
        "typ": "access",
        "sub": identity.subject,
        "role": "guest" if is_guest else "user",
        "name": identity.display_name,
        "iat": issued_at,
        "exp": issued_at + ttl,
        "jti": str(uuid4()),
    }
    if identity.family_id is not None:
        claims["family_id"] = str(identity.family_id)
    return jwt.encode(claims, secret, algorithm="HS256"), ttl


def decode_access_token(token: str, secret: str) -> AccessToken:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer="videocall",
            options={"require": ["iss", "typ", "sub", "name", "iat", "exp", "jti"]},
        )
        subject = claims["sub"]
        name = claims["name"]
        if claims["typ"] != "access" or not isinstance(subject, str) or not isinstance(name, str):
            raise ValueError
        if subject.startswith("guest:"):
            if "family_id" in claims:
                raise ValueError
            identity = Identity(UUID(subject.removeprefix("guest:")), name)
        else:
            identity = Identity(UUID(subject), name, UUID(claims["family_id"]))
        return AccessToken(
            identity,
            datetime.fromtimestamp(claims["iat"], UTC),
            datetime.fromtimestamp(claims["exp"], UTC),
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError(ErrorCode.TOKEN_EXPIRED) from exc
    except (
        jwt.InvalidTokenError,
        AttributeError,
        KeyError,
        OSError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise AuthError(ErrorCode.TOKEN_INVALID) from exc
