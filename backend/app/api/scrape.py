"""Scrape orchestration endpoints — start a scrape from the UI and poll
its progress for the "scan-style" toast on the homepage.

Heavy work runs as a FastAPI BackgroundTask (an asyncio task on the
same event loop, since uvicorn drives async). One scrape ≈ tens of
minutes for a full city; the response returns 202 immediately and the
ticker inside ``scraper.runner.run_spider`` keeps the DB row updated
for the polling status endpoint.
"""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import settings
from app.models.scrape_run import ScrapeRun
from app.schemas.scrape import (
    ScrapeRunResponse,
    ScrapeStatusResponse,
    ScrapeTriggerRequest,
    ScrapeTriggerResponse,
)

router = APIRouter(prefix="/api/scrape", tags=["scrape"])

# Window used to group per-portal runs into one logical "job" — anything
# started within the last hour is considered part of the current job
# (cf. the "latest batch" pattern in finance-alert's scan-status).
JOB_WINDOW = timedelta(hours=1)
# Runs started within this window of the newest run belong to the same
# logical job. A scrape spawns all its per-portal runs within ~1s, so a
# few minutes is a safe cluster boundary that won't merge two jobs.
JOB_CLUSTER = timedelta(minutes=3)
# Heartbeat threshold: a run with no progress update older than this is
# flagged as stale (worker died, network stuck, etc.).
STALE_AFTER = timedelta(seconds=120)

# Phase ordering — we surface the "least advanced" phase across portals
# so the UI shows the bottleneck (e.g. some are still searching while
# others moved to fetch).
_PHASE_ORDER = {"search": 0, "fetch": 1, "done": 2, "failed": 3}


@router.post("/trigger", response_model=ScrapeTriggerResponse, status_code=202)
async def trigger_scrape(request: ScrapeTriggerRequest) -> ScrapeTriggerResponse:
    """Kick off a scrape as a detached subprocess and return immediately.

    We launch ``python -m scraper.runner`` rather than a FastAPI
    BackgroundTask: a BackgroundTask lives inside the uvicorn process
    and dies the moment the API restarts (dev reloads, deploys). A
    detached subprocess keeps running and writes its progress to the
    shared SQLite DB via the heartbeat ticker — the status endpoint
    reads that, so the UI stays accurate across API restarts.

    Defaults: ``portal="all"`` runs every enabled portal; ``city``
    falls back to ``SCRAPE_DEFAULT_CITY`` (bari).
    """
    from scraper.runner import SPIDERS

    city = (request.city or settings.SCRAPE_DEFAULT_CITY).lower()

    if request.portal == "all":
        portals = list(SPIDERS.keys())
        args = [sys.executable, "-m", "scraper.runner", "--city", city]
    else:
        if request.portal not in SPIDERS:
            return ScrapeTriggerResponse(
                accepted=False,
                portals=[],
                city=city,
                started_at=datetime.now(timezone.utc).isoformat(),
                message=f"Portale sconosciuto: {request.portal}",
            )
        portals = [request.portal]
        args = [
            sys.executable, "-m", "scraper.runner",
            "--portal", request.portal, "--city", city,
        ]

    # backend/ is the cwd that makes `-m scraper.runner` resolve.
    backend_dir = Path(__file__).resolve().parents[2]
    creationflags = 0
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP — survives the
        # parent (uvicorn) being killed/reloaded.
        creationflags = 0x00000008 | 0x00000200

    subprocess.Popen(
        args,
        cwd=str(backend_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )

    return ScrapeTriggerResponse(
        accepted=True,
        portals=portals,
        city=city,
        started_at=datetime.now(timezone.utc).isoformat(),
        message=f"Scrape avviato per {', '.join(portals)}.",
    )


@router.get("/status", response_model=ScrapeStatusResponse)
async def scrape_status(db: AsyncSession = Depends(get_db)) -> ScrapeStatusResponse:
    """Aggregate the *current* scrape job's progress.

    A job = the cluster of per-portal runs kicked off together. We can't
    just take "everything in the last hour" because a killed job and a
    fresh one would be conflated (orphaned failed rows would drag the
    aggregate). Instead: find the most-recent run, then include only the
    runs whose ``started_at`` is within JOB_CLUSTER of it. A real job
    spawns its 6+ runs within the same second, so a few-minute window
    isolates it cleanly from anything that ran before.
    """
    cutoff = (datetime.now(timezone.utc) - JOB_WINDOW).isoformat()
    recent = (
        await db.execute(
            select(ScrapeRun)
            .where(ScrapeRun.started_at >= cutoff)
            .order_by(ScrapeRun.started_at.desc())
        )
    ).scalars().all()

    if not recent:
        return ScrapeStatusResponse(
            is_running=False,
            is_stale=False,
            progress_done=0,
            progress_total=0,
            runs=[],
        )

    # Group by the most-recent job_id. Every per-portal run of a single
    # `run_all_spiders` invocation shares one job_id, so this isolates
    # the current job from any prior (incl. orphaned) runs cleanly —
    # immune to how far apart in time the jobs were triggered.
    newest = max(recent, key=lambda r: r.started_at or "")
    target_job = newest.job_id
    if target_job:
        rows = [r for r in recent if r.job_id == target_job]
    else:
        # Legacy rows predating job_id — fall back to the time cluster.
        try:
            newest_dt = datetime.fromisoformat((newest.started_at or "").replace("Z", "+00:00"))
        except ValueError:
            newest_dt = datetime.now(timezone.utc)
        floor = newest_dt - JOB_CLUSTER
        rows = [
            r for r in recent
            if r.started_at
            and datetime.fromisoformat(r.started_at.replace("Z", "+00:00")) >= floor
        ]

    now = datetime.now(timezone.utc)
    is_running = any(r.status == "running" for r in rows)
    started_at = min((r.started_at for r in rows if r.started_at), default=None)
    finished_candidates = [r.finished_at for r in rows]
    finished_at = (
        max(finished_candidates) if all(f is not None for f in finished_candidates) else None
    )

    progress_done = sum(r.progress_done or 0 for r in rows)
    progress_total = sum(r.progress_total or 0 for r in rows)

    # Most-recent heartbeat across runs. Stale if any *running* row's
    # heartbeat is older than STALE_AFTER.
    last_progress_at = max(
        (r.last_progress_at for r in rows if r.last_progress_at),
        default=None,
    )
    seconds_since: int | None = None
    is_stale = False
    if last_progress_at:
        try:
            last_dt = datetime.fromisoformat(last_progress_at.replace("Z", "+00:00"))
            seconds_since = max(0, int((now - last_dt).total_seconds()))
        except ValueError:
            seconds_since = None
    if is_running:
        running_runs = [r for r in rows if r.status == "running" and r.last_progress_at]
        for r in running_runs:
            try:
                last_dt = datetime.fromisoformat(r.last_progress_at.replace("Z", "+00:00"))
                if (now - last_dt) > STALE_AFTER:
                    is_stale = True
                    break
            except ValueError:
                continue

    # Surface the *least-advanced* phase across running portals — that's
    # what dominates the wait time.
    running_phases = [r.phase for r in rows if r.status == "running" and r.phase]
    if running_phases:
        phase = min(running_phases, key=lambda p: _PHASE_ORDER.get(p, 99))
    elif is_running:
        phase = "search"  # default if heartbeat hasn't written yet
    else:
        phase = "done" if all(r.status != "running" for r in rows) else None

    return ScrapeStatusResponse(
        is_running=is_running,
        is_stale=is_stale,
        started_at=started_at,
        finished_at=finished_at if not is_running else None,
        seconds_since_last_progress=seconds_since,
        progress_done=progress_done,
        progress_total=progress_total,
        phase=phase,
        runs=[ScrapeRunResponse.model_validate(r) for r in rows],
    )


@router.get("/runs", response_model=list[ScrapeRunResponse])
async def list_recent_runs(db: AsyncSession = Depends(get_db)) -> list[ScrapeRunResponse]:
    """Recent run history — used by /admin pages and debugging."""
    result = await db.execute(
        select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(20)
    )
    runs = result.scalars().all()
    return [ScrapeRunResponse.model_validate(r) for r in runs]
