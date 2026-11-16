from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]

    @field_validator("text")
    @classmethod
    def valid_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Tin nhắn chứa ký tự không hợp lệ.")
        return value


class ChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: UUID | None
    sender_name: str
    content: str
    created_at: datetime


class ChatHistory(BaseModel):
    items: list[ChatMessage]
    next_before: int | None = None
