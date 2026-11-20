from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import User


def avatar_url(user: User, size: int = 64) -> str | None:
    return f"/media/avatars/{user.id}/{user.avatar_key}-{size}.webp" if user.avatar_key else None


class PublicUser(BaseModel):
    id: UUID
    display_name: str
    avatar_url: str | None

    @classmethod
    def from_user(cls, user: User):
        return cls(id=user.id, display_name=user.display_name, avatar_url=avatar_url(user))


class SearchUser(PublicUser):
    relationship: Literal["none", "friend", "request_sent", "request_received"]


class FriendItem(PublicUser):
    is_online: bool | None
    since: datetime


class RequestItem(BaseModel):
    id: UUID
    from_user: PublicUser = Field(serialization_alias="from")
    to: PublicUser
    status: Literal["pending", "accepted"] = "pending"
    created_at: datetime


class FriendPage(BaseModel):
    items: list[FriendItem]
    total: int
    page: int
    page_size: int


class BlockItem(BaseModel):
    user: PublicUser
    created_at: datetime


class SendFriendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_user_id: UUID


class BlockUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
