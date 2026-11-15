from fastapi import APIRouter, Response

from app.api.deps import DB, Auth, CurrentAccount, CurrentMember, CurrentPrincipal
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
        return MemberProfile.model_validate(principal.user)
    access = principal.access
    return GuestProfile(
        id=access.identity.subject,
        display_name=access.identity.display_name,
        created_at=access.issued_at,
        expires_at=access.expires_at,
    )


@router.patch("")
async def patch_me(body: UpdateProfileRequest, member: CurrentMember, db: DB) -> MemberProfile:
    user = await update_profile(db, member.user.id, body.display_name)
    return MemberProfile.model_validate(user)


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
