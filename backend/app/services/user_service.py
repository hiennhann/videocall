from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.models import User
from app.schemas.auth import UpdateProfileRequest


async def get_user(db: AsyncSession, user_id: UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise AuthError(ErrorCode.TOKEN_INVALID)
    return user


async def editable_user(db: AsyncSession, user_id: UUID | None, *, lock: bool = False) -> User:
    if user_id is None:
        raise AuthError(ErrorCode.GUEST_NOT_ALLOWED)
    statement = select(User).where(User.id == user_id).execution_options(populate_existing=True)
    user = await db.scalar(statement.with_for_update() if lock else statement)
    if user is None:
        raise AuthError(ErrorCode.TOKEN_INVALID)
    if not user.is_active:
        raise AuthError(ErrorCode.ACCOUNT_DISABLED)
    if user.must_change_password:
        raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
    return user


async def update_profile(db: AsyncSession, user_id: UUID, patch: UpdateProfileRequest) -> User:
    user = await editable_user(db, user_id)
    values = patch.model_dump(exclude_unset=True, exclude={"privacy"})
    if patch.birth_date is not None:
        today = datetime.now(UTC).date()
        try:
            oldest = today.replace(year=today.year - 120)
        except ValueError:  # Ngày 29/2 khi năm cận dưới không nhuận.
            oldest = date(today.year - 120, 2, 28)
        if not max(date(1900, 1, 1), oldest) <= patch.birth_date <= today:
            raise AuthError(
                ErrorCode.INVALID_BIRTH_DATE,
                fields={"birth_date": "Ngày sinh ngoài khoảng hợp lệ."},
            )
    if patch.privacy is not None:
        values.update(patch.privacy.model_dump(exclude_unset=True))
    if not values:
        return user
    user = await db.scalar(update(User).where(User.id == user_id).values(**values).returning(User))
    if user is None:
        raise AuthError(ErrorCode.TOKEN_INVALID)
    await db.commit()
    return user
