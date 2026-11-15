import asyncio
import hashlib
import hmac
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from starlette.datastructures import FormData

from app.api.deps import ADMIN_LIMIT, client_info, enforce_rate_limit
from app.core.errors import AuthError, ErrorCode
from app.core.security import decode_access_token, hash_refresh_token
from app.models import User
from app.services.auth_service import AuthService, SessionTokens

ACCESS_COOKIE = "vc_admin_access"
REFRESH_COOKIE = "vc_admin_refresh"
CSRF_COOKIE = "vc_admin_csrf"
COOKIE_FLAGS = {"path": "/admin", "httponly": True, "secure": True, "samesite": "strict"}
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"


@dataclass(frozen=True, slots=True)
class WebAdmin:
    user: User
    family_id: UUID


def redirect(request: Request, path: str) -> Response:
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=200, headers={"HX-Redirect": path})
    return RedirectResponse(path, status_code=303)


def _signature(secret: str, nonce: str, scope: str) -> str:
    return hmac.new(
        secret.encode(), f"admin-csrf:{scope}:{nonce}".encode(), hashlib.sha256
    ).hexdigest()


def new_csrf(secret: str, scope: str) -> str:
    nonce = secrets.token_urlsafe(32)
    return nonce + "." + _signature(secret, nonce, scope)


def valid_csrf(secret: str, value: str, scope: str) -> bool:
    nonce, dot, signature = value.partition(".")
    return bool(
        dot
        and len(nonce) == 43
        and signature.isascii()
        and hmac.compare_digest(signature, _signature(secret, nonce, scope))
    )


def set_csrf(response: Response, csrf: str, max_age: int = 900) -> None:
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, **COOKIE_FLAGS)


def set_session(response: Response, tokens: SessionTokens, csrf: str, ttl_days: int) -> None:
    ttl = ttl_days * 86400
    response.set_cookie(
        ACCESS_COOKIE, tokens.access_token, max_age=tokens.expires_in, **COOKIE_FLAGS
    )
    response.set_cookie(REFRESH_COOKIE, tokens.refresh_token, max_age=ttl, **COOKIE_FLAGS)
    set_csrf(response, csrf, ttl)


def clear_session(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, **COOKIE_FLAGS)


async def csrf_form(request: Request) -> FormData:
    form = await request.form()
    expected = request.cookies.get(CSRF_COOKIE, "")
    supplied = form.get("_csrf", "")
    origin = request.headers.get("origin")
    try:
        same_host = (
            origin is None or urlsplit(origin).netloc.casefold() == request.url.netloc.casefold()
        )
    except ValueError:
        same_host = False
    if (
        not isinstance(supplied, str)
        or not supplied.isascii()
        or not expected.isascii()
        or expected != request.state.admin_csrf
        or not hmac.compare_digest(supplied, expected)
        or not same_host
    ):
        raise AuthError(ErrorCode.FORBIDDEN)
    return form


class AdminSessions:
    def __init__(self) -> None:
        self._refreshing: dict[str, asyncio.Task[tuple[SessionTokens, int]]] = {}

    async def _load(self, request: Request, token: str) -> WebAdmin | None:
        service = request.app.state.auth_service
        access = decode_access_token(token, service.secret)
        family = access.identity.family_id
        if family is None:
            return None
        async with request.app.state.session_factory() as db:
            user = await db.get(User, access.identity.id)
            if user is None or not user.is_active or user.role != "admin":
                return None
            if not await AuthService.has_active_session(db, user.id, family):
                return None
            return WebAdmin(user, family)

    async def _rotate(self, request: Request, token: str) -> tuple[SessionTokens, int]:
        async with request.app.state.session_factory() as db:
            service = request.app.state.auth_service
            tokens = await service.refresh(db, token, client_info(request), admin_only=True)
            policy = await service.settings.get(db)
            return tokens, policy.refresh_token_ttl_days

    async def renew(self, request: Request, token: str) -> tuple[SessionTokens, int]:
        token_hash = hash_refresh_token(token)
        task = self._refreshing.get(token_hash)
        if task is None:
            task = asyncio.create_task(self._rotate(request, token))
            self._refreshing[token_hash] = task

            def finished(done: asyncio.Task[tuple[SessionTokens, int]]) -> None:
                if self._refreshing.get(token_hash) is done:
                    del self._refreshing[token_hash]
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def resolve(
        self, request: Request
    ) -> tuple[WebAdmin | None, tuple[SessionTokens, int] | None]:
        access = request.cookies.get(ACCESS_COOKIE)
        if access:
            try:
                return await self._load(request, access), None
            except AuthError as exc:
                if exc.code != ErrorCode.TOKEN_EXPIRED:
                    return None, None

        refresh = request.cookies.get(REFRESH_COOKIE)
        if not refresh or len(refresh) > 256:
            return None, None
        try:
            tokens, refresh_days = await self.renew(request, refresh)
            return await self._load(request, tokens.access_token), (tokens, refresh_days)
        except AuthError:
            return None, None


def install_admin_sessions(app: FastAPI) -> None:
    sessions = AdminSessions()

    @app.middleware("http")
    async def admin_session(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path != "/admin" and not path.startswith("/admin/"):
            return await call_next(request)
        if path.startswith("/admin/static/"):
            return await call_next(request)

        secret = request.app.state.auth_service.secret
        prior_csrf = request.cookies.get(CSRF_COOKIE, "")
        request.state.web_admin = None
        if path == "/admin/login":
            csrf = (
                prior_csrf if valid_csrf(secret, prior_csrf, "login") else new_csrf(secret, "login")
            )
            request.state.admin_csrf = csrf
            response = await call_next(request)
            if request.method == "GET" and prior_csrf != csrf:
                set_csrf(response, csrf)
        else:
            admin, renewed = await sessions.resolve(request)
            request.state.web_admin = admin
            if admin is None:
                response = redirect(request, "/admin/login")
            else:
                scope = str(admin.family_id)
                csrf = (
                    prior_csrf if valid_csrf(secret, prior_csrf, scope) else new_csrf(secret, scope)
                )
                request.state.admin_csrf = csrf
                request.state.admin_refresh_token = (
                    renewed[0].refresh_token if renewed else request.cookies.get(REFRESH_COOKIE)
                )
                if admin.user.must_change_password and path not in {
                    "/admin/password",
                    "/admin/logout",
                }:
                    response = redirect(request, "/admin/password")
                else:
                    try:
                        enforce_rate_limit(request, ADMIN_LIMIT, "admin", str(admin.user.id))
                    except AuthError as exc:
                        response = Response(
                            "Bạn đã gửi quá nhiều yêu cầu.",
                            status_code=429,
                            headers={"Retry-After": str(exc.retry_after)},
                        )
                    else:
                        response = await call_next(request)
                if path != "/admin/logout" or response.status_code >= 400:
                    if renewed is not None:
                        set_session(response, renewed[0], csrf, renewed[1])
                    elif prior_csrf != csrf:
                        set_csrf(response, csrf)

        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
