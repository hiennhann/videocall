from datetime import date, datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.auth import DisplayName


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName | None = None
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_null(self) -> "UserPatch":
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Các trường tài khoản phải có giá trị.")
        return self


class AdminUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    role: Literal["user", "admin"]
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class AdminUserDetail(AdminUser):
    active_sessions: int
    is_online: bool


class DailyUsers(BaseModel):
    date: date
    count: int


class Dashboard(BaseModel):
    online_connections: int
    active_rooms: int
    active_participants: int
    total_users: int
    new_users_per_day: list[DailyUsers]
    turn: Any | None = None


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: UUID | None
    actor_label: str
    action: str
    target_type: str | None
    target_id: str | None
    detail: dict[str, Any]
    ip: IPv4Address | IPv6Address | None
    created_at: datetime


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
