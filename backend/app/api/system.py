from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db.session import database_is_ready

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", responses={503: {"description": "Database unavailable or migration pending"}})
async def ready(request: Request) -> JSONResponse:
    if await database_is_ready(request.app.state.engine, request.app.state.migration_heads):
        return JSONResponse({"status": "ok"})
    return JSONResponse(
        {"error": {"code": "NOT_READY", "message": "Dịch vụ chưa sẵn sàng.", "details": {}}},
        status_code=503,
    )
