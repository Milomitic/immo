"""Scrape orchestration: start a scrape from the UI, poll its progress for
the homepage toast, and inspect what went wrong.

The scrape itself runs as a detached ``python -m scraper.runner`` process
(see app.services.scrape_service.launch_scrape) and reports through the
shared DB, so API restarts never interrupt it.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.config import settings
from app.models.scrape_run import ScrapeError, ScrapeRun
from app.schemas.scrape import (
    LastUpdateResponse,
    ScrapeErrorResponse,
    ScrapeRunResponse,
    ScrapeStatusResponse,
    ScrapeTriggerRequest,
    ScrapeTriggerResponse,
)
from app.services.scrape_service import (
    STALE_AFTER,
    enabled_portals,
    launch_scrape,
    reap_orphaned_runs,
    scrape_in_progress,
)

router = APIRouter(prefix="/scrape", tags=["scrape"])

# Only runs started within this window are candidates for "the current job".
JOB_WINDOW = timedelta(hours=1)
# Legacy rows without job_id: runs started within this window of the newest
# one are treated as the same job.
JOB_CLUSTER = timedelta(minutes=3)

# We surface the *least advanced* phase across portals — it's what
# dominates the remaining wait.
_PHASE_ORDER = {"search": 0, "fetch": 1, "done": 2, "failed": 3}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.post(
    "/trigger",
    response_model=ScrapeTriggerResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
async def trigger_scrape(
    request: ScrapeTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> ScrapeTriggerResponse:
    """Launch a scrape and return immediately (202). 409 if one is already
    running — two concurrent jobs would double the load on every portal and
    fight over the same rows."""
    from scraper.runner import SPIDERS  # heavy import (curl_cffi): keep lazy

    await reap_orphaned_runs(db)
    if await scrape_in_progress(db):
        raise HTTPException(status_code=409, detail="Una scansione è già in corso")

    city = (request.city or settings.SCRAPE_DEFAULT_CITY).lower()
    if request.portal == "all":
        portals = [p for p in enabled_portals() if p in SPIDERS]
        launch_scrape(city)
    elif request.portal in SPIDERS:
        portals = [request.portal]
        launch_scrape(city, request.portal)
    else:
        raise HTTPException(status_code=422, detail=f"Portale sconosciuto: {request.portal}")

    return ScrapeTriggerResponse(
        accepted=True,
        portals=portals,
        city=city,
        started_at=datetime.now(timezone.utc).isoformat(),
        message=f"Scansione avviata per {', '.join(portals)}.",
    )


@router.get("/status", response_model=ScrapeStatusResponse)
async def scrape_status(db: AsyncSession = Depends(get_db)) -> ScrapeStatusResponse:
    """Aggregate progress of the current job (all per-portal runs sharing
    the most recent ``job_id``) into one bar with one ETA."""
    await reap_orphaned_runs(db)

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
            is_running=False, is_stale=False, progress_done=0, progress_total=0, runs=[]
        )

    newest = max(recent, key=lambda r: r.started_at or "")
    if newest.job_id:
        rows = [r for r in recent if r.job_id == newest.job_id]
    else:
        floor = (_parse_ts(newest.started_at) or datetime.now(timezone.utc)) - JOB_CLUSTER
        rows = [r for r in recent if (_parse_ts(r.started_at) or floor) >= floor]

    now = datetime.now(timezone.utc)
    running = [r for r in rows if r.status == "running"]
    heartbeats = {r.id: _parse_ts(r.last_progress_at) for r in running}
    fresh = [r for r in running if heartbeats[r.id] and now - heartbeats[r.id] <= STALE_AFTER]
    # A running row with a stale heartbeat is a hung worker: still "running"
    # (the reaper only closes it after ORPHAN_AFTER) but flagged as stale.
    is_running = bool(running)
    is_stale = bool(running) and len(fresh) < len(running)

    last_hb = max((ts for ts in (_parse_ts(r.last_progress_at) for r in rows) if ts), default=None)
    seconds_since = max(0, int((now - last_hb).total_seconds())) if last_hb else None

    running_phases = [r.phase for r in running if r.phase]
    if running_phases:
        phase = min(running_phases, key=lambda p: _PHASE_ORDER.get(p, 99))
    elif is_running:
        phase = "search"
    else:
        phase = "done"

    # Progress units differ per phase (search pages, then detail pages):
    # while running, only sum the runs in the reported phase.
    in_phase = [r for r in running if r.phase == phase] if is_running else rows

    finished = [r.finished_at for r in rows]
    return ScrapeStatusResponse(
        is_running=is_running,
        is_stale=is_stale,
        started_at=min((r.started_at for r in rows if r.started_at), default=None),
        finished_at=None if is_running or None in finished else max(finished),
        seconds_since_last_progress=seconds_since,
        progress_done=sum(r.progress_done or 0 for r in in_phase),
        progress_total=sum(r.progress_total or 0 for r in in_phase),
        phase=phase,
        runs=[ScrapeRunResponse.model_validate(r) for r in rows],
    )


@router.get("/runs", response_model=list[ScrapeRunResponse])
async def list_recent_runs(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ScrapeRunResponse]:
    result = await db.execute(select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(limit))
    return [ScrapeRunResponse.model_validate(r) for r in result.scalars().all()]


_FINISHED = ("completed", "completed_with_errors")


@router.get("/last-update", response_model=LastUpdateResponse)
async def last_update(db: AsyncSession = Depends(get_db)) -> LastUpdateResponse:
    """The most recent finished scrape job, and each portal's latest
    finished run. Failed runs don't count as an update."""
    rows = (
        await db.execute(
            select(ScrapeRun.portal, func.max(ScrapeRun.finished_at))
            .where(ScrapeRun.status.in_(_FINISHED), ScrapeRun.finished_at.isnot(None))
            .group_by(ScrapeRun.portal)
        )
    ).all()
    by_portal = {portal: finished for portal, finished in rows}
    if not by_portal:
        return LastUpdateResponse()

    latest = (
        await db.execute(
            select(ScrapeRun)
            .where(ScrapeRun.status.in_(_FINISHED), ScrapeRun.finished_at.isnot(None))
            .order_by(ScrapeRun.finished_at.desc())
            .limit(1)
        )
    ).scalar_one()
    if latest.job_id:
        job = (
            await db.execute(
                select(ScrapeRun).where(
                    ScrapeRun.job_id == latest.job_id, ScrapeRun.status.in_(_FINISHED)
                )
            )
        ).scalars().all()
    else:  # legacy rows without job_id: the run alone
        job = [latest]
    portals = sorted({r.portal for r in job})
    return LastUpdateResponse(
        finished_at=max(r.finished_at for r in job),
        portals=portals,
        is_full=set(enabled_portals()) <= set(portals),
        by_portal=by_portal,
    )


@router.get("/runs/{run_id}/errors", response_model=list[ScrapeErrorResponse])
async def run_errors(run_id: str, db: AsyncSession = Depends(get_db)) -> list[ScrapeErrorResponse]:
    if await db.get(ScrapeRun, run_id) is None:
        raise HTTPException(status_code=404, detail="Run non trovato")
    result = await db.execute(
        select(ScrapeError).where(ScrapeError.run_id == run_id).order_by(ScrapeError.created_at)
    )
    return [ScrapeErrorResponse.model_validate(e) for e in result.scalars().all()]


@router.get("/errors", response_model=list[ScrapeErrorResponse])
async def recent_errors(
    portal: str | None = None,
    kind: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[ScrapeErrorResponse]:
    """Most recent failures, filterable — e.g. ``?portal=casa&kind=blocked``
    answers "is casa.it banning us?"."""
    query = select(ScrapeError).order_by(ScrapeError.created_at.desc()).limit(limit)
    if portal:
        query = query.where(ScrapeError.portal == portal)
    if kind:
        query = query.where(ScrapeError.kind == kind)
    result = await db.execute(query)
    return [ScrapeErrorResponse.model_validate(e) for e in result.scalars().all()]
