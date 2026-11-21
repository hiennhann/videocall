from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

type RoomCode = Annotated[str, Field(pattern=r"^[a-z]{3}-[a-z]{4}-[a-z]{3}$")]
type PeerId = Annotated[str, Field(min_length=1, max_length=128)]
type RoomPassword = Annotated[SecretStr, Field(min_length=4, max_length=64)]


class CreateRoom(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: Annotated[str, Field(max_length=100)] | None = None
    mode: Literal["meeting", "livestream"] = "meeting"
    is_private: bool = False
    password: RoomPassword | None = None
    max_participants: Annotated[int, Field(ge=2, le=50)] | None = None

    @model_validator(mode="after")
    def check_password(self) -> Self:
        if self.is_private != (self.password is not None):
            raise ValueError("Mật khẩu chỉ được đặt cho phòng riêng và phòng riêng cần mật khẩu.")
        return self


class RoomCreated(BaseModel):
    code: str
    name: str | None
    mode: str
    is_private: bool
    max_participants: int
    participants: int = 0
    host_id: UUID | None
    status: str
    created_at: datetime


class RoomSummary(BaseModel):
    code: str
    name: str | None
    mode: str
    has_password: bool
    participants: int
    max_participants: int
    status: str


class JoinRoom(BaseModel):
    invite_id: Annotated[UUID, Field(strict=False)] | None = None
    model_config = ConfigDict(extra="forbid", strict=True)

    code: RoomCode
    password: Annotated[SecretStr, Field(max_length=64)] | None = None


class PeerTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    peer_id: PeerId


class KickPeer(PeerTarget):
    reason: Annotated[str, Field(max_length=200)] | None = None


class MutePeer(PeerTarget):
    kind: Literal["audio", "video"]


class MediaState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    audio: bool
    video: bool
    screen: bool
    screen_stream_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None

    @model_validator(mode="after")
    def check_screen(self) -> Self:
        if self.screen != (self.screen_stream_id is not None):
            raise ValueError("Cần ID luồng khi đang chia sẻ màn hình.")
        return self


class AdminKick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peer_id: PeerId | None = None
    user_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None

    @model_validator(mode="after")
    def check_target(self) -> Self:
        if (self.peer_id is None) == (self.user_id is None):
            raise ValueError("Cần đúng một peer_id hoặc user_id.")
        return self


class SessionDescription(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["offer", "answer"]
    sdp: Annotated[str, Field(min_length=1, max_length=20 * 1024)]


class SignalDescription(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    to: PeerId
    sdp: SessionDescription


class IceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    candidate: Annotated[str, Field(max_length=2048)]
    sdpMid: str | None = None
    sdpMLineIndex: Annotated[int, Field(ge=0)] | None = None
    usernameFragment: str | None = None


class SignalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    to: PeerId
    candidate: IceCandidate
