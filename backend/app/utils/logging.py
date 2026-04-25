import logging
import sys
from pathlib import Path

import structlog

from app.config import settings


def setup_logging(log_file: str | Path | None = None) -> None:
    """Configure structlog.

    If `log_file` is provided, JSON logs are written to that file instead of
    stderr. The scraper CLI uses this so the rich Progress bars can own
    stderr without log lines stomping on the live display.
    """
    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Line-buffered append so tail -f works and nothing is lost on crash.
        sink = log_path.open("a", encoding="utf-8", buffering=1)
        logger_factory = structlog.PrintLoggerFactory(file=sink)
    else:
        logger_factory = structlog.PrintLoggerFactory(file=sys.stderr)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.LOG_LEVEL == "DEBUG" else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL, logging.INFO)
        ),
        context_class=dict,
        logger_factory=logger_factory,
        cache_logger_on_first_use=True,
    )
