from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

type MessageId = Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]


class DirectSend(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_user_id: UUID
    client_msg_id: UUID
    text: Annotated[
        str,
        StringConstraints(
            strict=True, strip_whitespace=True, min_length=1, max_length=2000, pattern=r"^[^\x00]+$"
        ),
    ]


class ReadUpTo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    up_to_id: MessageId


class DirectRead(ReadUpTo):
    conversation_id: UUID


class DirectTyping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_user_id: UUID
    typing: Annotated[bool, Field(strict=True)]
