from datetime import date, datetime
from typing import TYPE_CHECKING, Annotated, Literal, Self
from unicodedata import category
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)

if TYPE_CHECKING:
    from app.models import User


def normalize_email(value: str) -> str:
    normalized = value.lower()
    if len(normalized) > 254:
        raise ValueError("Email tối đa 254 ký tự.")
    return normalized


def clean_display_name(value: object) -> object:
    if isinstance(value, str):
        return "".join(char for char in value if category(char) != "Cc").strip()
    return value


type Email = Annotated[EmailStr, AfterValidator(normalize_email)]
type DisplayName = Annotated[
    str, BeforeValidator(clean_display_name), Field(min_length=2, max_length=50)
]
type Password = Annotated[SecretStr, Field(min_length=8, max_length=128)]
type SuppliedPassword = Annotated[SecretStr, Field(min_length=1, max_length=128)]


class RegisterRequest(BaseModel):
    email: Email
    display_name: DisplayName
    password: Password


class LoginRequest(BaseModel):
    email: Email
    password: SuppliedPassword
    client_type: Literal["web", "mobile"] = "mobile"


class DeviceTransferRequest(BaseModel):
    transfer_token: Annotated[SecretStr, Field(min_length=1, max_length=256)]
    client_type: Literal["web", "mobile"] = "mobile"


class RefreshRequest(BaseModel):
    refresh_token: Annotated[SecretStr, Field(max_length=256)]


class GuestRequest(BaseModel):
    display_name: DisplayName
    client_type: Literal["web", "mobile"] = "mobile"


class PrivacySettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    discoverable_by_email: bool = True
    show_online_status: bool = True


class PrivacyPatch(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    discoverable_by_email: bool | None = None
    show_online_status: bool | None = None

    @field_validator("discoverable_by_email", "show_online_status")
    @classmethod
    def reject_null(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("Quyền riêng tư phải là true hoặc false.")
        return value


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName | None = None
    birth_date: date | None = None
    privacy: PrivacyPatch | None = None

    @field_validator("display_name", "privacy")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Trường này không được null.")
        return value

    @field_validator("birth_date", mode="before")
    @classmethod
    def date_only(cls, value: object) -> object:
        if value is None or type(value) is date:
            return value
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("Ngày sinh phải có dạng YYYY-MM-DD.")
        return date.fromisoformat(value)


class ChangePasswordRequest(BaseModel):
    current_password: SuppliedPassword
    new_password: Password


class LoginUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    role: Literal["user", "admin"] = "user"
    must_change_password: bool = False


class RegisteredUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    role: Literal["user", "admin"] = "user"
    created_at: datetime


class MemberProfile(LoginUser):
    is_guest: Literal[False] = False
    created_at: datetime
    birth_date: date | None = None
    avatar_url: str | None = None
    avatar_thumb_url: str | None = None
    privacy: PrivacySettings

    @classmethod
    def from_user(cls, user: "User") -> Self:
        avatar = f"/media/avatars/{user.id}/{user.avatar_key}" if user.avatar_key else None
        return cls(
            **LoginUser.model_validate(user).model_dump(),
            created_at=user.created_at,
            birth_date=user.birth_date,
            avatar_url=f"{avatar}-256.webp" if avatar else None,
            avatar_thumb_url=f"{avatar}-64.webp" if avatar else None,
            privacy=PrivacySettings(
                discoverable_by_email=user.discoverable_by_email,
                show_online_status=user.show_online_status,
            ),
        )


class GuestUser(BaseModel):
    id: str
    display_name: str
    role: Literal["guest"] = "guest"


class GuestProfile(GuestUser):
    email: None = None
    is_guest: Literal[True] = True
    must_change_password: bool = False
    created_at: datetime
    expires_at: datetime


class AccessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class RefreshResponse(AccessResponse):
    refresh_token: str | None = None


class LoginResponse(RefreshResponse):
    user: LoginUser


class GuestResponse(AccessResponse):
    user: GuestUser
