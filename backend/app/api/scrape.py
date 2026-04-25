from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.scrape_run import ScrapeRun
from app.schemas.scrape import ScrapeRunResponse, ScrapeTriggerRequest, ScrapeTriggerResponse

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


@router.post("/trigger", response_model=ScrapeTriggerResponse)
async def trigger_scrape(
    request: ScrapeTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> ScrapeTriggerResponse:
    portals = (
        ["immobiliare", "idealista", "casa"]
        if request.portal == "all"
        else [request.portal]
    )

    run_ids = []
    for portal in portals:
        run = ScrapeRun(portal=portal, status="pending")
        db.add(run)
        await db.flush()
        run_ids.append(run.id)

    await db.commit()

    # TODO: trigger actual scraping via background task
    return ScrapeTriggerResponse(
        run_ids=run_ids,
        message=f"Scrape triggered for: {', '.join(portals)}",
    )


@router.get("/status", response_model=list[ScrapeRunResponse])
async def scrape_status(db: AsyncSession = Depends(get_db)) -> list[ScrapeRunResponse]:
    result = await db.execute(
        select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(20)
    )
    runs = result.scalars().all()
    return [ScrapeRunResponse.model_validate(r) for r in runs]
