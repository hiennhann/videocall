from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import DB
from app.db.session import database_is_ready
from app.metrics import Metrics

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


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request, db: DB) -> Response:
    metrics: Metrics = request.app.state.metrics
    connections, rooms, participants = await request.app.state.realtime.room_counts(db)
    metrics.connections.set(connections)
    metrics.rooms.set(rooms)
    metrics.participants.set(participants)
    return Response(
        generate_latest(metrics.registry),
        headers={"Content-Type": CONTENT_TYPE_LATEST, "Cache-Control": "no-store"},
    )
