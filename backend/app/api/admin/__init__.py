from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import AwareDatetime

from app.api.deps import DB, CurrentAdmin, OperationalSettings
from app.core.errors import AuthError, ErrorCode
from app.schemas.admin import (
    AdminUser,
    AdminUserDetail,
    AuditEntry,
    DailyUsers,
    Dashboard,
    Page,
    UserPatch,
)
from app.schemas.settings import PublicSettings, SettingsPatch
from app.services.admin_service import (
    AdminService,
    count_user_sessions,
    get_admin_target,
    list_users,
    user_counts,
)
from app.services.audit_service import list_audit
from app.services.settings_service import settings_metadata

router = APIRouter(prefix="/admin", tags=["admin"])
public_router = APIRouter(tags=["config"])

type PageNumber = Annotated[int, Query(ge=1)]
type PageSize = Annotated[int, Query(ge=1, le=100)]


async def get_admin_service(request: Request) -> AdminService:
    return request.app.state.admin_service


type AdminOps = Annotated[AdminService, Depends(get_admin_service)]


@public_router.get("/config/public")
async def public_config(db: DB, settings: OperationalSettings) -> PublicSettings:
    return PublicSettings.model_validate(await settings.get(db))


@router.get("/dashboard")
async def dashboard(actor: CurrentAdmin, db: DB, service: AdminOps) -> Dashboard:
    total, daily = await user_counts(db)
    connections, rooms, participants = await service.events.room_counts(db)
    return Dashboard(
        online_connections=connections,
        active_rooms=rooms,
        active_participants=participants,
        total_users=total,
        new_users_per_day=[DailyUsers(date=day, count=count) for day, count in daily],
    )


@router.get("/users")
async def users(
    actor: CurrentAdmin,
    db: DB,
    q: Annotated[str | None, Query(max_length=254)] = None,
    role: Literal["user", "admin"] | None = None,
    is_active: bool | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> Page[AdminUser]:
    rows, total = await list_users(
        db, q=q, role=role, is_active=is_active, page=page, page_size=page_size
    )
    return Page(
        items=[AdminUser.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}")
async def user_detail(
    user_id: UUID, actor: CurrentAdmin, db: DB, service: AdminOps
) -> AdminUserDetail:
    user = await get_admin_target(db, user_id)
    return AdminUserDetail(
        **AdminUser.model_validate(user).model_dump(),
        active_sessions=await count_user_sessions(db, user_id),
        is_online=service.events.is_online(user_id),
    )


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: UUID, body: UserPatch, actor: CurrentAdmin, db: DB, service: AdminOps
) -> AdminUser:
    user = await service.patch_user(db, actor, user_id, body.model_dump(exclude_unset=True))
    return AdminUser.model_validate(user)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: UUID, response: Response, actor: CurrentAdmin, db: DB, service: AdminOps
) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    return {"temporary_password": await service.reset_password(db, actor, user_id)}


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
async def revoke_sessions(
    user_id: UUID, actor: CurrentAdmin, db: DB, service: AdminOps
) -> Response:
    await service.revoke_sessions(db, actor, user_id)
    return Response(status_code=204)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: UUID, actor: CurrentAdmin, db: DB, service: AdminOps) -> Response:
    await service.delete_user(db, actor, user_id)
    return Response(status_code=204)


@router.get("/settings")
async def get_settings(
    actor: CurrentAdmin, db: DB, settings: OperationalSettings
) -> dict[str, dict[str, Any]]:
    return settings_metadata(await settings.get(db))


@router.patch("/settings")
async def patch_settings(
    body: SettingsPatch, actor: CurrentAdmin, db: DB, settings: OperationalSettings
) -> dict[str, dict[str, Any]]:
    return settings_metadata(await settings.patch(db, actor, body))


@router.get("/audit-logs")
async def audit_logs(
    actor: CurrentAdmin,
    db: DB,
    start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    actor_filter: Annotated[str | None, Query(alias="actor", max_length=254)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    target_type: Annotated[str | None, Query(max_length=32)] = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> Page[AuditEntry]:
    if start is not None and end is not None and start > end:
        raise AuthError(
            ErrorCode.VALIDATION_ERROR, fields={"to": "Phải từ thời điểm bắt đầu trở đi."}
        )
    rows, total = await list_audit(
        db,
        actor=actor_filter,
        action=action,
        target_type=target_type,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[AuditEntry.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
