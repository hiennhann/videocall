from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from limits import parse
from slowapi.util import get_remote_address

from app.api.deps import DB, CurrentAdmin, CurrentMember, CurrentPrincipal, enforce_rate_limit
from app.core.errors import AuthError, ErrorCode
from app.schemas.rooms import AdminKick, CreateRoom, RoomCreated, RoomSummary
from app.services.room_service import RoomService

router = APIRouter(prefix="/rooms", tags=["rooms"])
admin_router = APIRouter(prefix="/admin/rooms", tags=["admin"])
CREATE_LIMIT = parse("10/minute")
LOOKUP_LIMIT = parse("30/minute")


async def get_room_service(request: Request) -> RoomService:
    return request.app.state.realtime.rooms


type Rooms = Annotated[RoomService, Depends(get_room_service)]


@router.post("", status_code=201)
async def create_room(
    request: Request, body: CreateRoom, member: CurrentMember, db: DB, rooms: Rooms
) -> RoomCreated:
    enforce_rate_limit(request, CREATE_LIMIT, "rooms.create", str(member.user.id))
    return await rooms.create(db, member.user.id, body)


@router.get("/mine")
async def my_rooms(member: CurrentMember, db: DB, rooms: Rooms) -> list[RoomCreated]:
    return await rooms.mine(db, member.user.id)


@router.get("/{code}")
async def room_detail(
    request: Request, code: str, principal: CurrentPrincipal, db: DB, rooms: Rooms
) -> RoomSummary:
    if principal.user is not None and principal.user.must_change_password:
        raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
    enforce_rate_limit(request, LOOKUP_LIMIT, "rooms.detail", get_remote_address(request))
    return await rooms.detail(db, code)


@router.delete("/{code}", status_code=204)
async def close_room(code: str, member: CurrentMember, db: DB, rooms: Rooms) -> Response:
    await rooms.close(db, code, "host", user_id=str(member.user.id))
    return Response(status_code=204)


@admin_router.get("")
async def admin_rooms(actor: CurrentAdmin, db: DB, rooms: Rooms) -> list[dict[str, Any]]:
    return await rooms.admin_rooms(db)


@admin_router.delete("/{code}", status_code=204)
async def admin_close_room(code: str, actor: CurrentAdmin, db: DB, rooms: Rooms) -> Response:
    await rooms.close(db, code, "admin", actor=actor)
    return Response(status_code=204)


@admin_router.post("/{code}/kick", status_code=204)
async def admin_kick(
    code: str, body: AdminKick, actor: CurrentAdmin, db: DB, rooms: Rooms
) -> Response:
    await rooms.kick(db, code, peer_id=body.peer_id, user_id=body.user_id, actor=actor)
    return Response(status_code=204)
