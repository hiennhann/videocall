from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.api.deps import (
    DB,
    Auth,
    CurrentAccount,
    CurrentMember,
    CurrentPrincipal,
    OperationalSettings,
)
from app.core.errors import AuthError, ErrorCode
from app.schemas.auth import (
    ChangePasswordRequest,
    GuestProfile,
    MemberProfile,
    UpdateProfileRequest,
)
from app.services.user_service import update_profile

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def me(principal: CurrentPrincipal) -> MemberProfile | GuestProfile:
    if principal.user is not None:
        return MemberProfile.from_user(principal.user)
    access = principal.access
    return GuestProfile(
        id=access.identity.subject,
        display_name=access.identity.display_name,
        created_at=access.issued_at,
        expires_at=access.expires_at,
    )


@router.patch("")
async def patch_me(body: UpdateProfileRequest, member: CurrentMember, db: DB) -> MemberProfile:
    user = await update_profile(db, member.user.id, body)
    return MemberProfile.from_user(user)


async def read_avatar(request: Request, maximum: int) -> bytes:
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "multipart/form-data":
        raise AuthError(ErrorCode.INVALID_IMAGE)

    async def bounded_stream() -> AsyncIterator[bytes]:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > maximum + 16_384:  # Giới hạn cả phần header/boundary multipart.
                raise AuthError(ErrorCode.IMAGE_TOO_LARGE)
            yield chunk

    try:
        form = await MultiPartParser(
            request.headers, bounded_stream(), max_files=1, max_fields=0
        ).parse()
    except MultiPartException:
        raise AuthError(ErrorCode.INVALID_IMAGE) from None
    try:
        file = form.get("file")
        if len(form) != 1 or not isinstance(file, UploadFile):
            raise AuthError(ErrorCode.INVALID_IMAGE)
        data = await file.read(maximum + 1)
        if len(data) > maximum:
            raise AuthError(ErrorCode.IMAGE_TOO_LARGE)
        return data
    finally:
        await form.close()


@router.put(
    "/avatar",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def put_avatar(
    request: Request, member: CurrentMember, db: DB, settings: OperationalSettings
) -> MemberProfile:
    service = request.app.state.avatar_service
    policy = await settings.get(db)
    await service.upload_policy(db, member.user.id, policy)
    data = await read_avatar(request, policy.avatar_max_kb * 1024)
    user = await service.replace(db, member.user.id, data, policy)
    return MemberProfile.from_user(user)


@router.delete("/avatar", status_code=204)
async def delete_avatar(request: Request, member: CurrentMember, db: DB) -> Response:
    await request.app.state.avatar_service.delete(db, member.user.id)
    return Response(status_code=204)


@router.post("/password", status_code=204)
async def change_password(
    body: ChangePasswordRequest, member: CurrentAccount, db: DB, auth: Auth
) -> Response:
    await auth.change_password(
        db,
        member.user.id,
        member.family_id,
        body.current_password.get_secret_value(),
        body.new_password.get_secret_value(),
    )
    return Response(status_code=204)
