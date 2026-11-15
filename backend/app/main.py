import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.admin import public_router
from app.api.admin import router as admin_router
from app.api.auth import create_auth_router
from app.api.errors import (
    auth_error_handler,
    internal_error_handler,
    rate_limit_error_handler,
    validation_error_handler,
)
from app.api.me import router as me_router
from app.api.system import router as system_router
from app.core.config import Settings
from app.core.errors import AuthError
from app.core.security import hash_password
from app.db.session import migration_heads
from app.services.account_events import AccountEvents
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.settings_service import SettingsService


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.migration_heads = await asyncio.to_thread(migration_heads)
        dummy_hash = await hash_password(secrets.token_urlsafe(32))
        events = AccountEvents()
        app.state.settings_service = SettingsService()
        app.state.admin_service = AdminService(events)
        app.state.auth_service = AuthService(
            settings.jwt_secret.get_secret_value(), dummy_hash, app.state.settings_service, events
        )
        engine = create_async_engine(
            settings.database_url.get_secret_value(), pool_pre_ping=True, hide_parameters=True
        )
        app.state.engine = engine
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Video Call / Livestream", lifespan=lifespan)
    limiter = Limiter(key_func=get_remote_address, storage_uri="memory://", headers_enabled=True)
    app.state.limiter = limiter
    app.add_exception_handler(AuthError, auth_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_error_handler)
    app.add_exception_handler(Exception, internal_error_handler)
    app.include_router(system_router)
    app.include_router(create_auth_router(limiter), prefix="/api/v1")
    app.include_router(me_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(public_router, prefix="/api/v1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",")],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    @app.middleware("http")
    async def add_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    return app
