from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime

from app.api.admin import PageNumber, PageSize
from app.api.deps import DB, CurrentMember
from app.core.errors import AuthError, ErrorCode

router = APIRouter(prefix="/me/call-history", tags=["call history"])


def check_range(start: AwareDatetime | None, end: AwareDatetime | None) -> None:
    if start and end and start > end:
        raise AuthError(
            ErrorCode.VALIDATION_ERROR, fields={"to": "Phải từ thời điểm bắt đầu trở đi."}
        )


@router.get("")
async def listing(
    request: Request,
    member: CurrentMember,
    db: DB,
    type: Literal["hosted", "joined", "missed_invite"] | None = None,
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: AwareDatetime | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict:
    check_range(from_, to)
    return await request.app.state.realtime.history.listing(
        db, member.user.id, type, from_, to, page, page_size
    )


@router.get("/{code}")
async def detail(code: str, request: Request, member: CurrentMember, db: DB) -> dict:
    return await request.app.state.realtime.history.detail(db, code, member.user.id)


@router.get("/{code}/chat-export", response_class=StreamingResponse)
async def export(code: str, request: Request, member: CurrentMember, db: DB) -> StreamingResponse:
    lines = await request.app.state.realtime.history.export(db, code, member.user.id)
    return StreamingResponse(
        lines,
        media_type="text/plain",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="chat-{code}.txt"',
        },
    )


@router.delete("", status_code=204)
async def clear(request: Request, member: CurrentMember, db: DB) -> Response:
    await request.app.state.realtime.history.clear(db, member.user.id)
    return Response(status_code=204)
