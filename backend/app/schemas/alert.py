from typing import Any

from pydantic import BaseModel, Field


class AlertCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    # The /search query parameters, e.g. {"city": "bari", "price_max": "250000"}.
    filters: dict[str, Any] = Field(default_factory=dict)


class AlertUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    is_active: bool | None = None


class AlertResponse(BaseModel):
    id: str
    name: str
    filters: dict[str, Any]
    is_active: bool
    created_at: str
    seen_at: str | None = None
    last_notified_at: str | None = None
    total: int
    # Since seen_at: listings first seen after it, and price drops after it.
    new_count: int
    price_drop_count: int
