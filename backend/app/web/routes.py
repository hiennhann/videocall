from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from limits import parse
from pydantic import ValidationError
from slowapi.util import get_remote_address
from starlette.datastructures import FormData

from app.api.admin import AdminOps, PageSize
from app.api.deps import DB, Auth, OperationalSettings, client_info, enforce_rate_limit
from app.api.errors import AUTH_ERRORS
from app.api.rooms import Rooms
from app.core.config import DEMO_ADMIN_EMAIL
from app.core.errors import AuthError, ErrorCode
from app.core.security import decode_access_token
from app.schemas.admin import UserPatch
from app.schemas.auth import ChangePasswordRequest, LoginRequest
from app.schemas.rooms import AdminKick
from app.schemas.settings import SettingsSchema
from app.services.admin_service import (
    count_user_sessions,
    get_admin_target,
    list_users,
    user_counts,
)
from app.services.audit_service import AuditActor, list_audit
from app.services.settings_service import settings_metadata
from app.web.session import (
    WebAdmin,
    clear_session,
    csrf_form,
    install_admin_sessions,
    new_csrf,
    redirect,
    set_session,
)

WEB_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=WEB_ROOT / "templates")
LOGIN_LIMIT = parse("20/minute")
type Form = Annotated[FormData, Depends(csrf_form)]


def page(
    request: Request, template: str, title: str, *, status: int = 200, **context: Any
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name=template,
        status_code=status,
        context={
            "title": title,
            "admin": request.state.web_admin,
            "csrf": request.state.admin_csrf,
            **context,
        },
    )


class AdminRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def render(request: Request) -> Response:
            try:
                return await handler(request)
            except AuthError as error:
                status, message = AUTH_ERRORS[error.code]
                if request.url.path == "/admin/login":
                    response = page(
                        request, "login.html", "Đăng nhập quản trị", status=status, error=message
                    )
                else:
                    response = page(
                        request, "error.html", "Thao tác thất bại", status=status, error=message
                    )
                if error.retry_after is not None:
                    response.headers["Retry-After"] = str(error.retry_after)
                return response
            except (ValidationError, RequestValidationError):
                if request.url.path == "/admin/login":
                    return page(
                        request,
                        "login.html",
                        "Đăng nhập quản trị",
                        status=422,
                        error="Email hoặc mật khẩu không hợp lệ.",
                    )
                return page(
                    request,
                    "error.html",
                    "Dữ liệu không hợp lệ",
                    status=422,
                    error="Kiểm tra các trường rồi thử lại.",
                )

        return render


router = APIRouter(prefix="/admin", include_in_schema=False, route_class=AdminRoute)


async def current_admin(request: Request) -> WebAdmin:
    admin = request.state.web_admin
    if admin is None:
        raise AuthError(ErrorCode.FORBIDDEN)
    return admin


type Admin = Annotated[WebAdmin, Depends(current_admin)]


def actor(request: Request, admin: WebAdmin) -> AuditActor:
    return AuditActor(admin.user.id, admin.user.email, client_info(request).ip)


@router.get("/login")
async def login_form(request: Request) -> Response:
    return page(request, "login.html", "Đăng nhập quản trị")


@router.post("/login")
async def login(request: Request, form: Form, db: DB, auth: Auth) -> Response:
    enforce_rate_limit(request, LOGIN_LIMIT, "admin.login", get_remote_address(request))
    fields = dict(form)
    identifier = fields.get("email")
    if (
        request.app.state.demo_admin
        and isinstance(identifier, str)
        and identifier.strip().casefold() == "admin"
    ):
        fields["email"] = DEMO_ADMIN_EMAIL
    credentials = LoginRequest.model_validate(fields)
    user, tokens = await auth.login(
        db,
        credentials.email,
        credentials.password.get_secret_value(),
        client_info(request),
        admin_only=True,
    )
    policy = await auth.settings.get(db)
    response = redirect(request, "/admin/password" if user.must_change_password else "/admin")
    family = decode_access_token(tokens.access_token, auth.secret).identity.family_id
    set_session(response, tokens, new_csrf(auth.secret, str(family)), policy.refresh_token_ttl_days)
    return response


@router.post("/logout")
async def logout(request: Request, form: Form, db: DB, auth: Auth) -> Response:
    refresh = request.state.admin_refresh_token
    if refresh and len(refresh) <= 256:
        await auth.logout(db, refresh)
    response = redirect(request, "/admin/login")
    clear_session(response)
    return response


@router.get("/password")
async def password_form(request: Request, admin: Admin) -> Response:
    return page(request, "password.html", "Đổi mật khẩu")


@router.post("/password")
async def password(request: Request, form: Form, admin: Admin, db: DB, auth: Auth) -> Response:
    body = ChangePasswordRequest.model_validate(dict(form))
    await auth.change_password(
        db,
        admin.user.id,
        admin.family_id,
        body.current_password.get_secret_value(),
        body.new_password.get_secret_value(),
    )
    return redirect(request, "/admin")


@router.get("")
async def dashboard(request: Request, admin: Admin, db: DB, service: AdminOps) -> Response:
    total, daily = await user_counts(db)
    connections, rooms, participants = await service.events.room_counts(db)
    return page(
        request,
        "dashboard.html",
        "Tổng quan",
        active="dashboard",
        total=total,
        daily=daily,
        connections=connections,
        rooms=rooms,
        participants=participants,
    )


@router.get("/users")
async def users(
    request: Request,
    admin: Admin,
    db: DB,
    q: Annotated[str, Query(max_length=254)] = "",
    role: Literal["", "user", "admin"] = "",
    status: Literal["", "active", "locked"] = "",
    page_number: Annotated[int, Query(alias="page", ge=1)] = 1,
    page_size: PageSize = 20,
) -> Response:
    rows, total = await list_users(
        db,
        q=q,
        role=role or None,
        is_active=(status == "active") if status else None,
        page=page_number,
        page_size=page_size,
    )
    return page(
        request,
        "users.html",
        "Tài khoản",
        active="users",
        users=rows,
        total=total,
        q=q,
        role=role,
        status_filter=status,
        current_page=page_number,
        page_size=page_size,
    )


@router.get("/users/{user_id}")
async def user_detail(
    request: Request, user_id: UUID, admin: Admin, db: DB, service: AdminOps
) -> Response:
    user = await get_admin_target(db, user_id)
    return page(
        request,
        "user.html",
        user.display_name,
        active="users",
        user=user,
        sessions=await count_user_sessions(db, user_id),
        online=service.events.is_online(user_id),
    )


@router.post("/users/{user_id}")
async def update_user(
    request: Request, user_id: UUID, form: Form, admin: Admin, db: DB, service: AdminOps
) -> Response:
    values = {
        field: form[field] for field in ("display_name", "role", "is_active") if field in form
    }
    patch = UserPatch.model_validate(values)
    await service.patch_user(
        db, actor(request, admin), user_id, patch.model_dump(exclude_unset=True)
    )
    return redirect(request, f"/admin/users/{user_id}")


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    request: Request, user_id: UUID, form: Form, admin: Admin, db: DB, service: AdminOps
) -> Response:
    temporary = await service.reset_password(db, actor(request, admin), user_id)
    return page(
        request,
        "temporary-password.html",
        "Mật khẩu tạm",
        active="users",
        temporary=temporary,
        target_id=user_id,
    )


@router.post("/users/{user_id}/revoke")
async def revoke(
    request: Request, user_id: UUID, form: Form, admin: Admin, db: DB, service: AdminOps
) -> Response:
    await service.revoke_sessions(db, actor(request, admin), user_id)
    return redirect(request, f"/admin/users/{user_id}")


@router.post("/users/{user_id}/delete")
async def delete_user(
    request: Request, user_id: UUID, form: Form, admin: Admin, db: DB, service: AdminOps
) -> Response:
    await service.delete_user(db, actor(request, admin), user_id)
    return redirect(request, "/admin/users")


@router.get("/rooms")
async def rooms(request: Request, admin: Admin, db: DB, service: Rooms) -> Response:
    return page(
        request, "rooms.html", "Phòng đang mở", active="rooms", rooms=await service.admin_rooms(db)
    )


@router.post("/rooms/{code}/close")
async def close_room(
    request: Request, code: str, form: Form, admin: Admin, db: DB, service: Rooms
) -> Response:
    await service.close(db, code, "admin", actor=actor(request, admin))
    return redirect(request, "/admin/rooms")


@router.post("/rooms/{code}/kick")
async def kick(
    request: Request, code: str, form: Form, admin: Admin, db: DB, service: Rooms
) -> Response:
    target = AdminKick.model_validate({"peer_id": form.get("peer_id")})
    await service.kick(db, code, peer_id=target.peer_id, actor=actor(request, admin))
    return redirect(request, "/admin/rooms")


@router.get("/settings")
async def operational_settings(
    request: Request, admin: Admin, db: DB, settings: OperationalSettings
) -> Response:
    groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for key, field in settings_metadata(await settings.get(db)).items():
        groups.setdefault(field["category"], []).append((key, field))
    return page(request, "settings.html", "Cấu hình", active="settings", groups=groups)


def setting_value(key: str, form: FormData) -> str | bool | int | None:
    field = SettingsSchema.model_fields.get(key)
    if field is None:
        raise AuthError(ErrorCode.UNKNOWN_SETTING)
    if form.get("operation") == "reset":
        return None
    value = form.get("value")
    if isinstance(value, str):
        if field.annotation is bool:
            if value in ("true", "false"):
                return value == "true"
        elif field.annotation is int:
            try:
                return int(value)
            except ValueError:
                pass
        else:
            return value
    raise AuthError(ErrorCode.VALIDATION_ERROR, fields={key: "Giá trị không hợp lệ."})


@router.post("/settings/{key}")
async def update_setting(
    request: Request, key: str, form: Form, admin: Admin, db: DB, settings: OperationalSettings
) -> Response:
    await settings.patch(db, actor(request, admin), {key: setting_value(key, form)})
    return redirect(request, "/admin/settings")


def audit_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise AuthError(ErrorCode.VALIDATION_ERROR) from None
    return result if result.tzinfo else result.replace(tzinfo=UTC)


@router.get("/audit")
async def audit(
    request: Request,
    admin: Admin,
    db: DB,
    by: Annotated[str, Query(alias="actor", max_length=254)] = "",
    action: Annotated[str, Query(max_length=64)] = "",
    target_type: Annotated[str, Query(max_length=32)] = "",
    date_from: Annotated[str, Query(alias="from", max_length=40)] = "",
    date_to: Annotated[str, Query(alias="to", max_length=40)] = "",
    page_number: Annotated[int, Query(alias="page", ge=1)] = 1,
    page_size: PageSize = 20,
) -> Response:
    start, end = audit_date(date_from), audit_date(date_to)
    if start is not None and end is not None and start > end:
        raise AuthError(
            ErrorCode.VALIDATION_ERROR, fields={"to": "Phải từ thời điểm bắt đầu trở đi."}
        )
    rows, total = await list_audit(
        db,
        actor=by or None,
        action=action or None,
        target_type=target_type or None,
        start=start,
        end=end,
        page=page_number,
        page_size=page_size,
    )
    return page(
        request,
        "audit.html",
        "Nhật ký quản trị",
        active="audit",
        entries=rows,
        total=total,
        by=by,
        action=action,
        target_type=target_type,
        date_from=date_from,
        date_to=date_to,
        current_page=page_number,
        page_size=page_size,
    )


def mount_admin(app: FastAPI) -> None:
    app.mount("/admin/static", StaticFiles(directory=WEB_ROOT / "static"), name="admin-static")
    app.include_router(router)
    install_admin_sessions(app)
