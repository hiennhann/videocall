from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response

from app.api.admin import PageNumber, PageSize
from app.api.deps import DB, CurrentMember
from app.core.errors import AuthError, ErrorCode
from app.schemas.direct_messages import ReadUpTo

router = APIRouter(prefix="/conversations", tags=["direct messages"])
type Cursor = Annotated[int | None, Query(ge=0, le=2**63 - 1)]


@router.get("")
async def listing(
    request: Request,
    response: Response,
    member: CurrentMember,
    db: DB,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.realtime.dm.listing(db, member.user.id, page, page_size)


@router.get("/with/{user_id}")
async def with_user(
    user_id: UUID, request: Request, response: Response, member: CurrentMember, db: DB
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.realtime.dm.with_user(db, member.user.id, user_id)


@router.get("/{conversation_id}/messages")
async def history(
    conversation_id: UUID,
    request: Request,
    response: Response,
    member: CurrentMember,
    db: DB,
    before: Cursor = None,
    after: Cursor = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    if before is not None and after is not None:
        raise AuthError(ErrorCode.VALIDATION_ERROR)
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.realtime.dm.history(
        db, member.user.id, conversation_id, before, after, limit
    )


@router.post("/{conversation_id}/read", status_code=204)
async def mark_read(
    conversation_id: UUID, body: ReadUpTo, request: Request, member: CurrentMember, db: DB
) -> Response:
    await request.app.state.realtime.dm.read(db, member.user.id, conversation_id, body.up_to_id)
    return Response(status_code=204)


@router.delete("/{conversation_id}/messages/{message_id}", status_code=204)
async def remove(
    conversation_id: UUID,
    message_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    request: Request,
    member: CurrentMember,
    db: DB,
) -> Response:
    await request.app.state.realtime.dm.remove(db, member.user.id, conversation_id, message_id)
    return Response(status_code=204)
