from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

backend_root = Path(__file__).resolve().parents[2]
client_root = backend_root / "client"
if not client_root.is_dir():
    client_root = backend_root.parent / "client"


def mount_client(app: FastAPI) -> None:
    router = APIRouter(include_in_schema=False)

    @router.get("/")
    async def login_page() -> FileResponse:
        return FileResponse(client_root / "index.html")

    @router.get("/lobby")
    async def lobby_page() -> FileResponse:
        return FileResponse(client_root / "lobby.html")

    @router.get("/room")
    async def room_page() -> FileResponse:
        return FileResponse(client_root / "room.html")

    app.include_router(router)
    app.mount("/client", StaticFiles(directory=client_root), name="client")
