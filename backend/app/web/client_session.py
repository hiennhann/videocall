import posixpath
from collections.abc import Awaitable, Callable
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.api.auth import PAGE_ACCESS_COOKIE, PAGE_COOKIE_FLAGS
from app.api.deps import Principal, current_principal
from app.core.errors import AuthError

PAGES = {
    "/lobby": "lobby.html",
    "/rooms": "rooms.html",
    "/account": "account.html",
    "/friends": "friends.html",
    "/messages": "messages.html",
    "/history": "history.html",
    "/rooms/join": "join.html",
    "/rooms/create": "create.html",
    "/room": "room.html",
}


def protected_page(path: str) -> str | None:
    path = posixpath.normpath(path.replace("\\", "/"))
    if path in PAGES:
        return path
    if path.startswith("/client/"):
        name = posixpath.basename(path).casefold()
        return next((page for page, filename in PAGES.items() if filename == name), None)
    return None


async def page_principal(request: Request) -> Principal | None:
    token = request.cookies.get(PAGE_ACCESS_COOKIE)
    if not token or len(token) > 8192:
        return None
    try:
        async with request.app.state.session_factory() as db:
            principal = await current_principal(
                request,
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
                request.app.state.auth_service,
                db,
            )
            if principal.user is None:
                policy = await request.app.state.settings_service.get(db)
                if not policy.allow_guest or policy.maintenance_mode:
                    return None
            return principal
    except AuthError:
        return None


def install_client_sessions(app: FastAPI) -> None:
    @app.middleware("http")
    async def client_session(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        page = protected_page(request.url.path)
        if page is None:
            return await call_next(request)

        principal = await page_principal(request)
        if principal is None:
            target = page + ("?" + request.url.query if request.url.query else "")
            response = RedirectResponse(
                "/?" + urlencode({"next": target, "login_required": "1"}), status_code=303
            )
            response.delete_cookie(PAGE_ACCESS_COOKIE, **PAGE_COOKIE_FLAGS)
        elif (
            principal.user is not None
            and principal.user.must_change_password
            and page != "/account"
        ):
            response = RedirectResponse("/account", status_code=303)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie"
        return response
