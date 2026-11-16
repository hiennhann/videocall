import base64
import hmac
from time import time

from app.core.errors import AuthError, ErrorCode
from app.core.security import Identity
from app.schemas.settings import SettingsSchema
from app.schemas.turn import TurnCredentials


class TurnService:
    def __init__(self, secret: str, urls: str) -> None:
        self._secret = secret.encode()
        self._urls = [url.strip() for url in urls.split(",") if url.strip()]
        self._stun_urls = [url for url in self._urls if url.startswith(("stun:", "stuns:"))]
        self._has_turn = any(url.startswith(("turn:", "turns:")) for url in self._urls)

    def credentials(self, identity: Identity, policy: SettingsSchema) -> TurnCredentials:
        if not policy.turn_enabled or not self._has_turn:
            return TurnCredentials(urls=self._stun_urls)
        if identity.family_id is None and not policy.turn_allow_guests:
            raise AuthError(ErrorCode.GUEST_NOT_ALLOWED)

        ttl = policy.turn_credential_ttl_seconds
        username = f"{int(time()) + ttl}:{identity.id}"
        digest = hmac.digest(self._secret, username.encode(), "sha1")
        return TurnCredentials(
            urls=self._urls,
            username=username,
            credential=base64.b64encode(digest).decode(),
            ttl=ttl,
        )
