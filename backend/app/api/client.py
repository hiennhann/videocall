from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

backend_root = Path(__file__).resolve().parents[2]
client_root = backend_root / "client"
if not client_root.is_dir():
    client_root = backend_root.parent / "client"


class ClientFiles(StaticFiles):
    def __init__(self, *, dev: bool) -> None:
        super().__init__(directory=client_root)
        self.dev = dev

    async def get_response(self, path: str, scope: Scope) -> Response:
        if not self.dev and Path(path).name.casefold() == "styleguide.html":
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)


def mount_client(app: FastAPI, *, dev: bool = False) -> None:
    router = APIRouter(include_in_schema=False)

    @router.get("/")
    async def login_page() -> FileResponse:
        return FileResponse(client_root / "index.html")

    @router.get("/lobby")
    async def lobby_page() -> FileResponse:
        return FileResponse(client_root / "lobby.html")

    @router.get("/rooms")
    async def rooms_page() -> FileResponse:
        return FileResponse(client_root / "rooms.html")

    @router.get("/account")
    async def account_page() -> FileResponse:
        return FileResponse(client_root / "account.html")

    @router.get("/rooms/join")
    async def join_page() -> FileResponse:
        return FileResponse(client_root / "join.html")

    @router.get("/rooms/create")
    async def create_page() -> FileResponse:
        return FileResponse(client_root / "create.html")

    @router.get("/room")
    async def room_page() -> FileResponse:
        return FileResponse(client_root / "room.html")

    @router.get("/styleguide")
    @router.get("/client/styleguide.html")
    async def styleguide_page() -> FileResponse:
        if not dev:
            raise HTTPException(status_code=404)
        return FileResponse(
            client_root / "styleguide.html",
            headers={"Content-Security-Policy": "frame-ancestors 'none'"},
        )

    app.include_router(router)
    app.mount("/client", ClientFiles(dev=dev), name="client")
