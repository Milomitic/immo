from pydantic import BaseModel

from app.schemas.listing import ListingResponse


class FavoriteResponse(BaseModel):
    listing: ListingResponse
    created_at: str
