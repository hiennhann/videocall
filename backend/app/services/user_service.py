from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.models import User


async def get_user(db: AsyncSession, user_id: UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise AuthError(ErrorCode.TOKEN_INVALID)
    return user


async def update_profile(db: AsyncSession, user_id: UUID, display_name: str) -> User:
    user = await db.scalar(
        update(User).where(User.id == user_id).values(display_name=display_name).returning(User)
    )
    if user is None:
        raise AuthError(ErrorCode.TOKEN_INVALID)
    await db.commit()
    return user
