"""Optional error reporting (Sentry) and request metrics (Prometheus)."""

import time

import sentry_sdk
import structlog
from prometheus_client import CollectorRegistry, Histogram, ProcessCollector

from app.config import settings

logger = structlog.get_logger()

# Own registry rather than the global one: /metrics adds per-request
# families from the DB next to it, and tests can't collide with leftovers.
REGISTRY = CollectorRegistry()
ProcessCollector(registry=REGISTRY)  # CPU/memory/fds — Linux only, a no-op elsewhere

REQUEST_DURATION = Histogram(
    "immo_http_request_duration_seconds",
    "API request latency, by route template.",
    ["method", "route", "status"],
    registry=REGISTRY,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def init_sentry(component: str) -> None:
    """Report unhandled errors to Sentry when SENTRY_DSN is set; no-op
    otherwise. ``component`` ("api" / "scraper") tags every event."""
    if not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("component", component)
    logger.info("sentry_enabled", component=component)


class MetricsMiddleware:
    """Time every HTTP request, labelled by the matched route *template*
    (``/api/v1/listings/{listing_id}``), never the raw path — one series
    per listing id would grow without bound."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500  # what the client gets if the app raises

        async def send_with_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            # The router stores the matched route in the (shared) scope.
            route = getattr(scope.get("route"), "path", None) or "unmatched"
            REQUEST_DURATION.labels(scope["method"], route, f"{status // 100}xx").observe(
                time.perf_counter() - start
            )
