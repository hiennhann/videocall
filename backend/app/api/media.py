import asyncio
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/media/avatars", tags=["media"])


@router.get("/{user_id}/{key}-{size}.webp")
async def avatar(
    request: Request,
    user_id: UUID,
    key: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
    size: Literal["256", "64"],
) -> FileResponse:
    path = request.app.state.avatar_service.path(user_id, key, int(size))
    if not await asyncio.to_thread(path.is_file):
        raise HTTPException(status_code=404)
    return FileResponse(
        path,
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
