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
    SCRAPE_RATE_LIMIT_RPM: int = 60  # 1 request/sec - safe for search pages
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
    LISTING_INACTIVE_DAYS: int = 14

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        extra="ignore",
    )


settings = Settings()
