import logging
from time import perf_counter
from uuid import uuid4

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bound_contextvars

logger = logging.getLogger(__name__)
HTTP_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "TRACE"}


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.http_requests = Counter(
            "http_requests_total",
            "HTTP responses by method, route and status.",
            ("method", "route", "status"),
            registry=self.registry,
        )
        self.http_latency = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds.",
            ("method", "route"),
            registry=self.registry,
        )
        self.connections = Gauge(
            "socket_connections", "Current Socket.IO connections.", registry=self.registry
        )
        self.presence_online_users = Gauge(
            "presence_online_users",
            "Registered accounts with an active socket.",
            registry=self.registry,
        )
        self.dm_messages = Counter(
            "dm_messages_total",
            "New direct messages committed.",
            registry=self.registry,
        )
        self.call_invites = Counter(
            "call_invites_total",
            "Committed call invitation transitions.",
            ("status",),
            registry=self.registry,
        )
        self.rooms = Gauge("rooms_active", "Current active rooms.", registry=self.registry)
        self.participants = Gauge(
            "room_participants", "Participants across all rooms.", registry=self.registry
        )
        self.socket_events = Counter(
            "socket_events_total",
            "Socket.IO events handled by the app.",
            ("event",),
            registry=self.registry,
        )
        self.socket_errors = Counter(
            "socket_errors_total", "Socket.IO errors by code.", ("code",), registry=self.registry
        )
        self.room_joins = Counter(
            "room_joins_total", "Successful room admissions.", registry=self.registry
        )
        self.room_kicks = Counter(
            "room_kicks_total", "Participants kicked.", registry=self.registry
        )
        self.rooms_created = Counter(
            "rooms_created_total", "Rooms created.", registry=self.registry
        )
        self.join_latency = Histogram(
            "join_room_duration_seconds", "Duration of join_room attempts.", registry=self.registry
        )


class HttpObservability:
    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        raw_method = scope["method"]
        method = raw_method if raw_method in HTTP_METHODS else "OTHER"
        status = 500
        started = perf_counter()

        async def observe_response(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        with bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, observe_response)
            finally:
                # FastAPI keeps router prefixes on the effective route of an included router.
                route_context = scope.get("fastapi", {}).get("effective_route_context")
                route = getattr(route_context or scope.get("route"), "path_format", None)
                route = route or "unmatched"
                if route != "/metrics":
                    elapsed = perf_counter() - started
                    self.metrics.http_requests.labels(method, route, str(status)).inc()
                    self.metrics.http_latency.labels(method, route).observe(elapsed)
                    fields = {
                        "method": method,
                        "route": route,
                        "status": status,
                        "duration_ms": round(elapsed * 1000, 2),
                    }
                    if state.get("user_id"):
                        fields["user_id"] = state["user_id"]
                    logger.log(
                        logging.ERROR if status >= 500 else logging.INFO,
                        "http_request",
                        extra=fields,
                    )
