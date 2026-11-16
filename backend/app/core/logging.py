import logging
import sys
from typing import Any

from structlog.contextvars import merge_contextvars
from structlog.processors import JSONRenderer, TimeStamper
from structlog.stdlib import ExtraAdder, ProcessorFormatter, add_log_level

LOG_FIELDS = {
    "request_id",
    "user_id",
    "method",
    "route",
    "status",
    "duration_ms",
    "socket_event",
    "code",
}


def add_request_field(_logger: Any, _method: str, event: dict[str, Any]) -> dict[str, Any]:
    event.setdefault("request_id", None)
    return event


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ProcessorFormatter(
            foreign_pre_chain=[
                ExtraAdder(allow=LOG_FIELDS),
                merge_contextvars,
                add_log_level,
                TimeStamper(fmt="iso", utc=True),
                add_request_field,
            ],
            processors=[ProcessorFormatter.remove_processors_meta, JSONRenderer()],
        )
    )
    logging.basicConfig(handlers=[handler], level=level, force=True)
    uvicorn = logging.getLogger("uvicorn")
    uvicorn.handlers.clear()
    uvicorn.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
