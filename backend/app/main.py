import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.admin import public_router
from app.api.admin import router as admin_router
from app.api.auth import create_auth_router
from app.api.call_history import router as call_history_router
from app.api.client import mount_client
from app.api.direct_messages import router as direct_messages_router
from app.api.errors import (
    auth_error_handler,
    internal_error_handler,
    rate_limit_error_handler,
    validation_error_handler,
)
from app.api.friends import router as friends_router
from app.api.invites import router as invites_router
from app.api.me import router as me_router
from app.api.media import router as media_router
from app.api.rooms import admin_router as admin_rooms_router
from app.api.rooms import router as rooms_router
from app.api.system import router as system_router
from app.api.turn import router as turn_router
from app.core.config import Settings
from app.core.errors import AuthError
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.session import migration_heads
from app.metrics import HttpObservability, Metrics
from app.realtime.server import RealtimeServer
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.avatar_service import AvatarService
from app.services.settings_service import SettingsService
from app.services.turn_service import TurnService
from app.sfu.control import SfuClient
from app.web.routes import mount_admin


def create_app() -> FastAPI:
    settings = Settings()
    if settings.env != "test":
        configure_logging(settings.log_level)
    metrics = Metrics()
    origins = [origin.strip() for origin in settings.allowed_origins.split(",")]
    operational_settings = SettingsService()
    sfu = (
        SfuClient(settings.sfu_url, settings.turn_secret.get_secret_value())
        if settings.sfu_url
        else None
    )
    avatars = AvatarService(settings.avatar_storage_dir)
    realtime = RealtimeServer(origins, operational_settings, sfu, metrics)
    if settings.env != "test":
        realtime.avatar_maintenance = avatars

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.migration_heads = await asyncio.to_thread(migration_heads)
        dummy_hash = await hash_password(secrets.token_urlsafe(32))
        app.state.settings_service = operational_settings
        app.state.admin_service = AdminService(realtime)
        app.state.auth_service = AuthService(
            settings.jwt_secret.get_secret_value(), dummy_hash, operational_settings, realtime
        )
        engine = create_async_engine(
            settings.database_url.get_secret_value(), pool_pre_ping=True, hide_parameters=True
        )
        app.state.engine = engine
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        realtime.start(app.state.session_factory, app.state.auth_service)
        try:
            await realtime.recover_history()
            yield
        finally:
            try:
                await realtime.stop()
            finally:
                await engine.dispose()

    app = FastAPI(title="Video Call / Livestream", lifespan=lifespan)
    app.state.demo_admin = settings.env == "dev"
    app.state.realtime = realtime
    app.state.friend_service = realtime.friends
    app.state.metrics = metrics
    app.state.avatar_service = avatars
    app.state.turn_service = TurnService(
        settings.turn_secret.get_secret_value(), settings.turn_urls
    )
    limiter = Limiter(key_func=get_remote_address, storage_uri="memory://", headers_enabled=True)
    app.state.limiter = limiter
    app.add_exception_handler(AuthError, auth_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_error_handler)
    app.add_exception_handler(Exception, internal_error_handler)
    app.include_router(system_router)
    app.include_router(create_auth_router(limiter), prefix="/api/v1")
    app.include_router(me_router, prefix="/api/v1")
    app.include_router(friends_router, prefix="/api/v1")
    app.include_router(invites_router, prefix="/api/v1")
    app.include_router(direct_messages_router, prefix="/api/v1")
    app.include_router(call_history_router, prefix="/api/v1")
    app.include_router(media_router)
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(public_router, prefix="/api/v1")
    app.include_router(rooms_router, prefix="/api/v1")
    app.include_router(admin_rooms_router, prefix="/api/v1")
    app.include_router(turn_router, prefix="/api/v1")
    mount_client(app, dev=settings.env == "dev")
    mount_admin(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    app.add_middleware(HttpObservability, metrics=metrics)
    return app


def create_asgi_app() -> socketio.ASGIApp:
    app = create_app()
    return socketio.ASGIApp(app.state.realtime.sio, other_asgi_app=app)
