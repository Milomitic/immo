from pydantic import BaseModel


class ScrapeTriggerRequest(BaseModel):
    portal: str = "all"  # immobiliare, idealista, casa, all
    city: str | None = None


class ScrapeTriggerResponse(BaseModel):
    run_ids: list[str]
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

    model_config = {"from_attributes": True}
