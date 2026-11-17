from datetime import datetime
from typing import Annotated, Literal
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
)


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


class UpdateProfileRequest(BaseModel):
    display_name: DisplayName


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
