from fastapi import APIRouter, Request, Response
from slowapi import Limiter

from app.api.deps import DB, Auth, CurrentMember, client_info
from app.schemas.auth import (
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

    @router.post("/login")
    @limiter.limit("20/minute")
    async def login(
        request: Request, response: Response, body: LoginRequest, db: DB, auth: Auth
    ) -> LoginResponse:
        user, tokens = await auth.login(
            db, body.email, body.password.get_secret_value(), client_info(request)
        )
        response.headers["Cache-Control"] = "no-store"
        return LoginResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            user=LoginUser.model_validate(user),
        )

    @router.post("/refresh")
    @limiter.limit("30/minute")
    async def refresh(
        request: Request, response: Response, body: RefreshRequest, db: DB, auth: Auth
    ) -> RefreshResponse:
        tokens = await auth.refresh(db, body.refresh_token.get_secret_value(), client_info(request))
        response.headers["Cache-Control"] = "no-store"
        return RefreshResponse.model_validate(tokens)

    @router.post("/logout", status_code=204)
    async def logout(body: RefreshRequest, db: DB, auth: Auth) -> Response:
        await auth.logout(db, body.refresh_token.get_secret_value())
        return Response(status_code=204)

    @router.post("/logout-all", status_code=204)
    async def logout_all(member: CurrentMember, db: DB, auth: Auth) -> Response:
        await auth.logout_all(db, member.user.id)
        return Response(status_code=204)

    @router.post("/guest")
    @limiter.limit("10/minute")
    async def guest(
        request: Request, response: Response, body: GuestRequest, auth: Auth, db: DB
    ) -> GuestResponse:
        identity, token, ttl = await auth.guest(db, body.display_name)
        response.headers["Cache-Control"] = "no-store"
        return GuestResponse(
            access_token=token,
            expires_in=ttl,
            user=GuestUser(id=identity.subject, display_name=identity.display_name),
        )

    return router
