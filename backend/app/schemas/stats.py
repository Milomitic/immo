from pydantic import BaseModel

from app.schemas.scrape import ScrapeRunResponse


class StatsResponse(BaseModel):
    total_listings: int
    active_listings: int
    by_portal: dict[str, int]
    by_city: dict[str, int]
    avg_price_sqm_by_city: dict[str, float]
    last_scrape_runs: list[ScrapeRunResponse]
