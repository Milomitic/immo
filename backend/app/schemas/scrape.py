from pydantic import BaseModel


class ScrapeTriggerRequest(BaseModel):
    portal: str = "all"  # immobiliare, idealista, casa, tecnocasa, remax, gabetti, vistocasa, all
    city: str | None = None


class ScrapeTriggerResponse(BaseModel):
    accepted: bool = True
    portals: list[str]
    city: str
    started_at: str
    message: str


class ScrapeRunResponse(BaseModel):
    id: str
    portal: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    listings_found: int
    listings_new: int
    listings_updated: int
    listings_deactivated: int
    errors: int
    # Live progress fields — surface what the heartbeat ticker writes
    # in runner.py so the frontend toast can render an ETA.
    progress_done: int | None = None
    progress_total: int | None = None
    phase: str | None = None
    last_progress_at: str | None = None
    # Coverage: how many listings the search pages showed, and whether the
    # whole catalog was walked (gates stale-listing deactivation).
    listings_seen: int | None = None
    coverage_complete: bool | None = None
    job_id: str | None = None

    model_config = {"from_attributes": True}


class ScrapeErrorResponse(BaseModel):
    id: str
    run_id: str
    portal: str
    kind: str
    url: str | None = None
    status_code: int | None = None
    message: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


class LastUpdateResponse(BaseModel):
    """When the catalogue was last refreshed. A job may have covered only
    some portals (a single-portal run), so ``is_full`` says whether every
    enabled portal was in it and ``by_portal`` gives each one's own date."""
    finished_at: str | None = None
    portals: list[str] = []
    is_full: bool = False
    by_portal: dict[str, str] = {}


class ScrapeStatusResponse(BaseModel):
    """Aggregated status of the most recent scrape *job* — the set of
    per-portal runs sharing a common start window. Designed to drive a
    single progress toast in the UI: one bar, one ETA, regardless of
    how many spiders are running in parallel.
    """
    is_running: bool
    is_stale: bool  # heartbeat older than STALE_AFTER seconds
    started_at: str | None = None
    finished_at: str | None = None  # latest run's finished_at (only when all done)
    seconds_since_last_progress: int | None = None
    progress_done: int  # sum across portals
    progress_total: int  # sum across portals
    phase: str | None = None  # most-advanced phase across portals
    runs: list[ScrapeRunResponse]  # per-portal breakdown
