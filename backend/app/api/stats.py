from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.listing import Listing
from app.models.scrape_run import ScrapeRun
from app.schemas.scrape import ScrapeRunResponse
from app.schemas.stats import StatsResponse

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)) -> StatsResponse:
    # Total and active listings
    total = (await db.execute(select(func.count(Listing.id)))).scalar() or 0
    active = (
        await db.execute(select(func.count(Listing.id)).where(Listing.is_active == True))
    ).scalar() or 0

    # By portal
    portal_result = await db.execute(
        select(Listing.source_portal, func.count(Listing.id))
        .where(Listing.is_active == True)
        .group_by(Listing.source_portal)
    )
    by_portal = {row[0]: row[1] for row in portal_result.all()}

    # By city (top 20)
    city_result = await db.execute(
        select(Listing.city, func.count(Listing.id))
        .where(Listing.is_active == True)
        .group_by(Listing.city)
        .order_by(func.count(Listing.id).desc())
        .limit(20)
    )
    by_city = {row[0]: row[1] for row in city_result.all()}

    # Average price/sqm by city (top 20 cities)
    avg_result = await db.execute(
        select(Listing.city, func.avg(Listing.price_per_sqm))
        .where(Listing.is_active == True, Listing.price_per_sqm.isnot(None))
        .group_by(Listing.city)
        .order_by(func.count(Listing.id).desc())
        .limit(20)
    )
    avg_price_sqm = {row[0]: round(row[1], 2) for row in avg_result.all() if row[1]}

    # Last scrape runs
    runs_result = await db.execute(
        select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(10)
    )
    last_runs = [ScrapeRunResponse.model_validate(r) for r in runs_result.scalars().all()]

    return StatsResponse(
        total_listings=total,
        active_listings=active,
        by_portal=by_portal,
        by_city=by_city,
        avg_price_sqm_by_city=avg_price_sqm,
        last_scrape_runs=last_runs,
    )
