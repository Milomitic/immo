from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is one level up from backend/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DB_PATH = _PROJECT_ROOT / "data" / "immo.db"


class Settings(BaseSettings):
    DATABASE_URL: str = f"sqlite+aiosqlite:///{_DB_PATH}"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:52048", "http://localhost:8001"]
    LOG_LEVEL: str = "INFO"

    # Scraping
    # Periodic scans are opt-in: every run hits the portals for a good while
    # (and casa.it bans aggressive clients), so the backend never starts one
    # on its own unless this is turned on.
    SCRAPE_SCHEDULE_ENABLED: bool = False
    SCRAPE_INTERVAL_HOURS: int = 6
    SCRAPE_DEFAULT_CITY: str = "bari"
    SCRAPE_DEFAULT_LISTING_TYPE: str = "sale"
    SCRAPE_IMMOBILIARE_ENABLED: bool = True
    SCRAPE_IDEALISTA_ENABLED: bool = False  # DataDome blocks all paths
    SCRAPE_CASA_ENABLED: bool = True
    SCRAPE_TECNOCASA_ENABLED: bool = True
    SCRAPE_REMAX_ENABLED: bool = True
    SCRAPE_GABETTI_ENABLED: bool = True
    SCRAPE_VISTOCASA_ENABLED: bool = True
    SCRAPE_WIKICASA_ENABLED: bool = True
    SCRAPE_SUBITO_ENABLED: bool = True
    SCRAPE_RATE_LIMIT_RPM: int = 60  # default for portals not listed below
    # Per-portal overrides. casa.it's WAF bans the IP after aggressive runs,
    # so it gets half the default budget.
    SCRAPE_RATE_LIMITS: dict[str, int] = {
        "immobiliare": 90,
        "casa": 30,
        "tecnocasa": 60,
        "remax": 60,
        "gabetti": 60,
        "vistocasa": 90,
        # Behind Cloudflare, which turns some requests away (403) at 40/min.
        "wikicasa": 30,
        # DataDome-protected: one page every 5s, and only search pages
        # (the spider never opens a listing).
        "subito": 12,
    }
    # Upper bound on search pages per path. Spiders follow the site's own
    # page count up to this; immobiliare offers ~100 pages for Bari, so the
    # old cap of 50 silently hid half its catalog.
    SCRAPE_MAX_PAGES: int = 200
    # Consecutive failed requests after which a spider stops hitting the
    # portal for the rest of the run (blocked / down) instead of digging
    # its ban deeper.
    SCRAPE_CIRCUIT_BREAKER_THRESHOLD: int = 8
    SCRAPE_REQUEST_DELAY_MIN: float = 0.5
    SCRAPE_REQUEST_DELAY_MAX: float = 2.0
    # Concurrent detail-fetches per spider. The RateLimiter still caps
    # requests-per-minute, so concurrency just lets us fill that budget in
    # parallel instead of serially with fixed delays.
    SCRAPE_CONCURRENCY: int = 4
    # NOTE: the old SCRAPE_FRESH_HOURS knob has been removed. Spiders now
    # skip the detail-page fetch for *any* source_id already in the DB
    # (regardless of age) — first observation is treated as immutable so
    # the original snapshot survives subsequent runs. last_seen_at still
    # gets bumped via `bump_last_seen` so LISTING_INACTIVE_DAYS keeps
    # working.

    # Skip listings first published more than N days ago (0 = keep all).
    # Off by default: an old listing that's still on sale is still a
    # listing a buyer cares about, and we're building a history.
    SCRAPE_MAX_LISTING_AGE_DAYS: int = 0

    # Deduplication
    DEDUP_THRESHOLD: float = 0.85
    # A listing not seen on any portal for this many days is deactivated
    # (only for portals whose last run had full coverage — see ScrapeRun).
    LISTING_INACTIVE_DAYS: int = 14

    # If set, mutating endpoints (scrape trigger, …) require the header
    # ``X-Admin-Token: <value>``. Leave empty for local single-user use.
    ADMIN_TOKEN: str = ""

    # Saved-search e-mail digests, sent after each scrape job. Optional:
    # nothing is sent unless SMTP_HOST and ALERT_EMAIL_TO are both set.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    SMTP_FROM: str = ""
    ALERT_EMAIL_TO: str = ""
    # Where links in e-mails point.
    FRONTEND_URL: str = "http://localhost:3000"

    # Observability. /metrics serves Prometheus metrics (catalogue size,
    # scrape outcomes and errors, API latency); turn it off if the API is
    # exposed publicly. Unhandled errors of the API and the scraper go to
    # Sentry when SENTRY_DSN is set.
    METRICS_ENABLED: bool = True
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        extra="ignore",
    )


settings = Settings()
