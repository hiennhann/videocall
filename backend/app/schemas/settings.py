from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class SettingsSchema(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    allow_registration: bool = Field(
        True, description="Cho phép tự đăng ký.", json_schema_extra={"category": "access"}
    )
    allow_guest: bool = Field(
        True, description="Cho phép đăng nhập khách.", json_schema_extra={"category": "access"}
    )
    guest_ttl_minutes: int = Field(
        120,
        ge=10,
        le=1440,
        description="Thời hạn token khách (phút).",
        json_schema_extra={"category": "access"},
    )
    maintenance_mode: bool = Field(
        False,
        description="Bảo trì, chặn tạo phòng và khách mới.",
        json_schema_extra={"category": "access"},
    )
    maintenance_message: str = Field(
        "",
        max_length=200,
        description="Thông báo bảo trì.",
        json_schema_extra={"category": "access"},
    )

    max_participants_per_room: int = Field(
        4,
        ge=2,
        le=50,
        description="Số người tối đa trong một phòng.",
        json_schema_extra={"category": "rooms"},
    )
    max_rooms_per_user: int = Field(
        3,
        ge=1,
        le=20,
        description="Số phòng đang mở của mỗi tài khoản.",
        json_schema_extra={"category": "rooms"},
    )
    room_empty_ttl_seconds: int = Field(
        300,
        ge=30,
        le=86400,
        description="Thời gian chờ đóng phòng trống (giây).",
        json_schema_extra={"category": "rooms"},
    )
    allow_screen_share: bool = Field(
        True, description="Cho phép chia sẻ màn hình.", json_schema_extra={"category": "rooms"}
    )
    chat_enabled: bool = Field(
        True, description="Cho phép gửi tin nhắn.", json_schema_extra={"category": "rooms"}
    )
    chat_history_enabled: bool = Field(
        True, description="Lưu lịch sử chat.", json_schema_extra={"category": "rooms"}
    )
    chat_retention_days: int = Field(
        30,
        ge=1,
        le=365,
        description="Thời hạn giữ lịch sử chat (ngày).",
        json_schema_extra={"category": "rooms"},
    )

    max_video_bitrate_kbps: int = Field(
        1500,
        ge=100,
        le=8000,
        description="Bitrate camera tối đa (kbps).",
        json_schema_extra={"category": "media"},
    )
    max_screen_bitrate_kbps: int = Field(
        2500,
        ge=200,
        le=10000,
        description="Bitrate chia sẻ màn hình tối đa (kbps).",
        json_schema_extra={"category": "media"},
    )
    max_video_resolution: Literal["360p", "480p", "720p", "1080p"] = Field(
        "720p", description="Độ phân giải camera tối đa.", json_schema_extra={"category": "media"}
    )
    default_codec: Literal["VP8", "VP9", "H264"] = Field(
        "VP8", description="Codec video ưu tiên.", json_schema_extra={"category": "media"}
    )

    turn_enabled: bool = Field(
        True, description="Cho phép dùng TURN.", json_schema_extra={"category": "turn"}
    )
    turn_credential_ttl_seconds: int = Field(
        14400,
        ge=300,
        le=86400,
        description="Thời hạn credential TURN (giây).",
        json_schema_extra={"category": "turn"},
    )
    turn_allow_guests: bool = Field(
        True, description="Cấp credential TURN cho khách.", json_schema_extra={"category": "turn"}
    )

    access_token_ttl_minutes: int = Field(
        15,
        ge=5,
        le=120,
        description="Thời hạn access token (phút).",
        json_schema_extra={"category": "security"},
    )
    refresh_token_ttl_days: int = Field(
        7,
        ge=1,
        le=90,
        description="Thời hạn refresh token (ngày).",
        json_schema_extra={"category": "security"},
    )
    password_min_length: int = Field(
        8,
        ge=8,
        le=64,
        description="Độ dài mật khẩu tối thiểu.",
        json_schema_extra={"category": "security"},
    )
    login_max_attempts: int = Field(
        5,
        ge=3,
        le=20,
        description="Số lần đăng nhập sai trước khi khóa tạm.",
        json_schema_extra={"category": "security"},
    )
    login_lockout_minutes: int = Field(
        15,
        ge=1,
        le=1440,
        description="Thời gian khóa tạm (phút).",
        json_schema_extra={"category": "security"},
    )


class PublicSettings(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    allow_registration: bool
    allow_guest: bool
    maintenance_mode: bool
    maintenance_message: str
    password_min_length: int
    allow_screen_share: bool
    chat_enabled: bool


type SettingValue = bool | int | str
type SettingsPatch = Annotated[dict[str, SettingValue | None], Field(strict=True)]
