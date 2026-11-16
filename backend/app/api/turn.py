from fastapi import APIRouter, Request, Response
from limits import parse

from app.api.deps import DB, CurrentPrincipal, OperationalSettings, enforce_rate_limit
from app.core.errors import AuthError, ErrorCode
from app.schemas.turn import TurnCredentials
from app.services.turn_service import TurnService

router = APIRouter(tags=["turn"])
TURN_LIMIT = parse("10/minute")


@router.get("/turn-credentials")
async def get_turn_credentials(
    request: Request,
    response: Response,
    principal: CurrentPrincipal,
    db: DB,
    settings: OperationalSettings,
) -> TurnCredentials:
    if principal.user is not None and principal.user.must_change_password:
        raise AuthError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
    identity = principal.access.identity
    enforce_rate_limit(request, TURN_LIMIT, "turn.credentials", identity.subject)
    response.headers["Cache-Control"] = "no-store"
    service: TurnService = request.app.state.turn_service
    return service.credentials(identity, await settings.get(db))
