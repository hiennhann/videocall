from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from limits import parse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DB, CurrentMember, enforce_rate_limit

router = APIRouter(tags=["invites"])
INVITE_LIMIT = parse("20/minute")


class SendInvites(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_ids: list[UUID] = Field(min_length=1, max_length=20)


@router.post("/rooms/{code}/invites", status_code=201)
async def send_invites(
    code: str, body: SendInvites, request: Request, member: CurrentMember, db: DB
) -> dict:
    enforce_rate_limit(request, INVITE_LIMIT, "call_invite", str(member.user.id))
    return await request.app.state.realtime.invites.send(db, member.user.id, code, body.user_ids)


@router.get("/invites")
async def inbox(
    request: Request, member: CurrentMember, db: DB, status: Literal["pending"] = "pending"
) -> dict:
    return {"items": await request.app.state.realtime.invites.inbox(db, member.user.id)}


@router.post("/invites/{invite_id}/decline", status_code=204)
async def decline(invite_id: UUID, request: Request, member: CurrentMember, db: DB) -> Response:
    await request.app.state.realtime.invites.decline(db, member.user.id, invite_id)
    return Response(status_code=204)


@router.delete("/rooms/{code}/invites/{invite_id}", status_code=204)
async def cancel(
    code: str, invite_id: UUID, request: Request, member: CurrentMember, db: DB
) -> Response:
    await request.app.state.realtime.invites.cancel(db, member.user.id, code, invite_id)
    return Response(status_code=204)
