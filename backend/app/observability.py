"""Optional error reporting (Sentry) and request metrics (Prometheus)."""

import time

import sentry_sdk
import structlog
from fastapi import Request
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


_ROUTE_KEY = "immo.route"


class MetricsMiddleware:
    """Time every HTTP request, labelled by the matched route *template*
    (``/api/v1/listings/{listing_id}``), never the raw path — one series
    per listing id would grow without bound.

    The template comes from ``record_route``, a global dependency: only
    inside the endpoint is the matched route known (FastAPI ≥ 0.14x
    resolves included routers in a child scope the middleware never sees).
    Requests that match no endpoint (404, 405) are "unmatched"."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500  # what the client gets if the app raises
        # Shared by reference with the endpoint's scope, even when that
        # scope is a copy of this one.
        matched: dict[str, str] = {}
        scope[_ROUTE_KEY] = matched

        async def send_with_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            REQUEST_DURATION.labels(
                scope["method"], matched.get("template", "unmatched"), f"{status // 100}xx"
            ).observe(time.perf_counter() - start)


async def record_route(request: Request) -> None:
    """Global dependency: hand the matched route's template to
    MetricsMiddleware."""
    matched = request.scope.get(_ROUTE_KEY)
    route = request.scope.get("route")
    if matched is None or route is None:
        return
    template = getattr(route, "path_format", None) or getattr(route, "path", "")
    # Routes of an included router may carry their path without the
    # include prefix (/api/v1, /api): it's whatever precedes the route in
    # the URL. Rendering the template with the request's own parameters
    # finds that boundary exactly.
    try:
        rendered = template.format(**request.path_params)
    except (KeyError, IndexError, ValueError):
        rendered = ""
    path = request.scope.get("path", "")
    prefix = path[: -len(rendered)] if rendered and path.endswith(rendered) else ""
    matched["template"] = prefix + template
