import hmac
import logging
from typing import Literal

import httpx

from app.core.errors import AuthError, ErrorCode
from app.schemas.rooms import SessionDescription

logger = logging.getLogger(__name__)
type Mode = Literal["publish", "view"]


def control_token(secret: str) -> str:
    return hmac.new(secret.encode(), b"videocall-sfu-control-v1", "sha256").hexdigest()


class SfuClient:
    def __init__(self, url: str, secret: str) -> None:
        self.http = httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {control_token(secret)}"},
            timeout=8,
            trust_env=False,
        )

    async def offer(
        self, room: str, peer_id: str, mode: Mode, sdp: SessionDescription
    ) -> SessionDescription:
        try:
            response = await self.http.put(
                f"/rooms/{room}/{peer_id}", json={"mode": mode, "sdp": sdp.sdp}
            )
            match response.status_code:
                case 409:
                    raise AuthError(ErrorCode.STREAM_NOT_READY)
                case 422:
                    raise AuthError(ErrorCode.INVALID_PAYLOAD)
            response.raise_for_status()
            return SessionDescription.model_validate(response.json())
        except httpx.HTTPError:
            raise AuthError(ErrorCode.SFU_UNAVAILABLE) from None

    async def remove(self, room: str, peer_id: str | None = None) -> None:
        path = f"/rooms/{room}/{peer_id}" if peer_id else f"/rooms/{room}"
        try:
            response = await self.http.delete(path, timeout=2)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Không thể đóng kết nối SFU qua dịch vụ nội bộ.")
