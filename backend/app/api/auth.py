from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response
from slowapi import Limiter

from app.api.deps import DB, Auth, CurrentMember, client_info
from app.core.errors import AuthError, ErrorCode
from app.models import User
from app.schemas.auth import (
    DeviceTransferRequest,
    GuestRequest,
    GuestResponse,
    GuestUser,
    LoginRequest,
    LoginResponse,
    LoginUser,
    RefreshRequest,
    RefreshResponse,
    RegisteredUser,
    RegisterRequest,
)
from app.services.auth_service import SessionTokens

REFRESH_COOKIE = "vc_user_refresh"
COOKIE_FLAGS = {"path": "/api/v1/auth", "httponly": True, "secure": True, "samesite": "strict"}
PAGE_ACCESS_COOKIE = "vc_user_page_access"
PAGE_COOKIE_FLAGS = {"path": "/", "httponly": True, "secure": True, "samesite": "strict"}


def require_same_origin(request: Request) -> None:
    try:
        origin = urlsplit(request.headers.get("origin", ""))
        if origin.scheme in {"http", "https"} and origin.netloc == request.url.netloc:
            return
    except ValueError:
        pass
    raise AuthError(ErrorCode.FORBIDDEN)


async def refresh_value(
    response: Response, tokens: SessionTokens, db: DB, auth: Auth, *, use_cookie: bool
) -> str | None:
    response.headers["Cache-Control"] = "no-store"
    if not use_cookie:
        return tokens.refresh_token
    response.set_cookie(
        PAGE_ACCESS_COOKIE, tokens.access_token, max_age=tokens.expires_in, **PAGE_COOKIE_FLAGS
    )
    policy = await auth.settings.get(db)
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=policy.refresh_token_ttl_days * 86400,
        **COOKIE_FLAGS,
    )
    return None


async def login_response(
    response: Response, result: tuple[User, SessionTokens], db: DB, auth: Auth, *, use_cookie: bool
) -> LoginResponse:
    user, tokens = result
    return LoginResponse(
        access_token=tokens.access_token,
        refresh_token=await refresh_value(response, tokens, db, auth, use_cookie=use_cookie),
        expires_in=tokens.expires_in,
        user=LoginUser.model_validate(user),
    )


def create_auth_router(limiter: Limiter) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/register", status_code=201)
    @limiter.limit("5/hour")
    async def register(
        request: Request, response: Response, body: RegisterRequest, db: DB, auth: Auth
    ) -> RegisteredUser:
        user = await auth.register(
            db, body.email, body.display_name, body.password.get_secret_value()
        )
        return RegisteredUser.model_validate(user)

    @router.post("/login", response_model_exclude_none=True)
    @limiter.limit("20/minute")
    async def login(
        request: Request, response: Response, body: LoginRequest, db: DB, auth: Auth
    ) -> LoginResponse:
        use_cookie = body.client_type == "web"
        if use_cookie:
            require_same_origin(request)
        result = await auth.login(
            db,
            body.email,
            body.password.get_secret_value(),
            client_info(request),
            use_cookie=use_cookie,
        )
        return await login_response(response, result, db, auth, use_cookie=use_cookie)

    @router.post("/device-transfer/confirm", response_model_exclude_none=True)
    @limiter.limit("20/minute")
    async def confirm_transfer(
        request: Request, response: Response, body: DeviceTransferRequest, db: DB, auth: Auth
    ) -> LoginResponse:
        use_cookie = body.client_type == "web"
        if use_cookie:
            require_same_origin(request)
        result = await auth.confirm_device_transfer(
            db, body.transfer_token.get_secret_value(), client_info(request), use_cookie=use_cookie
        )
        return await login_response(response, result, db, auth, use_cookie=use_cookie)

    @router.post("/device-transfer/cancel", status_code=204)
    @limiter.limit("20/minute")
    async def cancel_transfer(
        request: Request, body: DeviceTransferRequest, db: DB, auth: Auth
    ) -> Response:
        if body.client_type == "web":
            require_same_origin(request)
        await auth.cancel_device_transfer(db, body.transfer_token.get_secret_value())
        return Response(status_code=204)

    @router.post("/refresh", response_model_exclude_none=True)
    @limiter.limit("30/minute")
    async def refresh(
        request: Request, response: Response, db: DB, auth: Auth, body: RefreshRequest | None = None
    ) -> RefreshResponse:
        use_cookie = body is None
        if use_cookie:
            require_same_origin(request)
        token = (
            body.refresh_token.get_secret_value() if body else request.cookies.get(REFRESH_COOKIE)
        )
        if not token or len(token) > 256:
            raise AuthError(ErrorCode.INVALID_REFRESH_TOKEN)
        tokens = await auth.refresh(db, token, client_info(request))
        return RefreshResponse(
            access_token=tokens.access_token,
            refresh_token=await refresh_value(response, tokens, db, auth, use_cookie=use_cookie),
            expires_in=tokens.expires_in,
        )

    @router.post("/logout", status_code=204)
    async def logout(
        request: Request, db: DB, auth: Auth, body: RefreshRequest | None = None
    ) -> Response:
        if body is None:
            require_same_origin(request)
        token = (
            body.refresh_token.get_secret_value() if body else request.cookies.get(REFRESH_COOKIE)
        )
        if token and len(token) <= 256:
            await auth.logout(db, token)
        response = Response(status_code=204)
        if body is None:
            response.delete_cookie(REFRESH_COOKIE, **COOKIE_FLAGS)
            response.delete_cookie(PAGE_ACCESS_COOKIE, **PAGE_COOKIE_FLAGS)
        return response

    @router.post("/logout-all", status_code=204)
    async def logout_all(member: CurrentMember, db: DB, auth: Auth) -> Response:
        await auth.logout_all(db, member.user.id)
        return Response(status_code=204)

    @router.post("/guest")
    @limiter.limit("10/minute")
    async def guest(
        request: Request, response: Response, body: GuestRequest, auth: Auth, db: DB
    ) -> GuestResponse:
        if body.client_type == "web":
            require_same_origin(request)
        identity, token, ttl = await auth.guest(db, body.display_name)
        response.headers["Cache-Control"] = "no-store"
        if body.client_type == "web":
            response.set_cookie(PAGE_ACCESS_COOKIE, token, max_age=ttl, **PAGE_COOKIE_FLAGS)
            response.delete_cookie(REFRESH_COOKIE, **COOKIE_FLAGS)
        return GuestResponse(
            access_token=token,
            expires_in=ttl,
            user=GuestUser(id=identity.subject, display_name=identity.display_name),
        )

    return router
