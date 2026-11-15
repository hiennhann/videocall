from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class AccountEvents:
    """Các điểm tích hợp vòng đời tài khoản với realtime."""

    async def sessions_revoked(
        self,
        user_id: UUID,
        reason: str,
        *,
        only_family: UUID | None = None,
        keep_family: UUID | None = None,
    ) -> None:
        pass

    async def close_owned_rooms(self, db: AsyncSession, user_id: UUID, now: datetime) -> list[str]:
        return []

    async def owned_rooms_closed(self, codes: list[str]) -> None:
        pass

    def is_online(self, user_id: UUID) -> bool:
        return False

    async def room_counts(self, db: AsyncSession) -> tuple[int, int, int]:
        return 0, 0, 0
