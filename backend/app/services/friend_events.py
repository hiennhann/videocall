from uuid import UUID

from app.schemas.friends import RequestItem


class FriendEvents:
    """Điểm tích hợp bạn bè với realtime; thông báo được gửi sau commit."""

    async def request_received(self, recipient: UUID, request: RequestItem) -> None:
        pass

    async def friendship_added(self, first: UUID, second: UUID) -> None:
        pass

    async def friendship_removed(self, first: UUID, second: UUID, *, notify: UUID | None) -> None:
        pass

    def is_online(self, user_id: UUID) -> bool:
        return False
