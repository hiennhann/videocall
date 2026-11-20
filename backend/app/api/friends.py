from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from limits import parse
from slowapi.util import get_remote_address

from app.api.deps import DB, CurrentMember, enforce_rate_limit
from app.schemas.auth import Email
from app.schemas.friends import (
    BlockItem,
    BlockUser,
    FriendItem,
    FriendPage,
    RequestItem,
    SearchUser,
    SendFriendRequest,
)
from app.services.friend_service import FriendService

router = APIRouter(tags=["friends"])


def friend_service(request: Request) -> FriendService:
    return request.app.state.friend_service


type Friends = Annotated[FriendService, Depends(friend_service)]


@router.get("/users/search")
async def search_users(
    request: Request,
    member: CurrentMember,
    db: DB,
    service: Friends,
    email: Annotated[Email, Query()],
) -> dict[str, list[SearchUser]]:
    for limit, scope, key in (
        ("20/minute", "friend_search_user", str(member.user.id)),
        ("200/day", "friend_search_user", str(member.user.id)),
        ("60/minute", "friend_search_ip", get_remote_address(request)),
        ("600/day", "friend_search_ip", get_remote_address(request)),
    ):
        enforce_rate_limit(request, parse(limit), scope, key)
    return {"items": await service.search(db, member.user.id, email)}


@router.post("/friends/requests", status_code=201)
async def send_request(
    request: Request, body: SendFriendRequest, member: CurrentMember, db: DB, service: Friends
) -> RequestItem:
    enforce_rate_limit(request, parse("10/minute"), "friend_request_user", str(member.user.id))
    enforce_rate_limit(
        request, parse("30/minute"), "friend_request_ip", get_remote_address(request)
    )
    return await service.send(db, member.user.id, body.to_user_id)


@router.get("/friends/requests")
async def requests(
    member: CurrentMember,
    db: DB,
    service: Friends,
    direction: Literal["incoming", "outgoing"] = "incoming",
) -> dict[str, list[RequestItem]]:
    return {"items": await service.requests(db, member.user.id, direction)}


@router.post("/friends/requests/{request_id}/accept")
async def accept_request(
    request_id: UUID, member: CurrentMember, db: DB, service: Friends
) -> FriendItem:
    return await service.accept(db, member.user.id, request_id)


@router.post("/friends/requests/{request_id}/decline", status_code=204)
async def decline_request(
    request_id: UUID, member: CurrentMember, db: DB, service: Friends
) -> Response:
    await service.dismiss(db, member.user.id, request_id)
    return Response(status_code=204)


@router.delete("/friends/requests/{request_id}", status_code=204)
async def cancel_request(
    request_id: UUID, member: CurrentMember, db: DB, service: Friends
) -> Response:
    await service.dismiss(db, member.user.id, request_id, cancel=True)
    return Response(status_code=204)


@router.get("/friends")
async def list_friends(
    member: CurrentMember,
    db: DB,
    service: Friends,
    q: Annotated[str | None, Query(max_length=50)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FriendPage:
    return await service.friends(db, member.user.id, q=q, page=page, page_size=page_size)


@router.delete("/friends/{user_id}", status_code=204)
async def remove_friend(user_id: UUID, member: CurrentMember, db: DB, service: Friends) -> Response:
    await service.remove(db, member.user.id, user_id)
    return Response(status_code=204)


@router.get("/blocks")
async def list_blocks(
    member: CurrentMember, db: DB, service: Friends
) -> dict[str, list[BlockItem]]:
    return {"items": await service.blocks(db, member.user.id)}


@router.post("/blocks", status_code=201)
async def block_user(body: BlockUser, member: CurrentMember, db: DB, service: Friends) -> BlockItem:
    return await service.block(db, member.user.id, body.user_id)


@router.delete("/blocks/{user_id}", status_code=204)
async def unblock_user(user_id: UUID, member: CurrentMember, db: DB, service: Friends) -> Response:
    await service.unblock(db, member.user.id, user_id)
    return Response(status_code=204)
