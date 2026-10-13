from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.listing import _now, _uuid


class SearchAlert(Base):
    """A saved search. ``filters`` holds the /search query parameters as
    JSON. What counts as new is relative to ``seen_at`` (the user's last
    look, moved by "segna come visti"); e-mail digests have their own
    watermark, ``last_notified_at``, and only go out while ``is_active``."""

    __tablename__ = "search_alerts"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    name: Mapped[str | None] = mapped_column(Text)
    filters: Mapped[str | None] = mapped_column(Text)  # JSON
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_notified_at: Mapped[str | None] = mapped_column(Text)
    seen_at: Mapped[str | None] = mapped_column(Text, default=_now)
    created_at: Mapped[str] = mapped_column(Text, default=_now)
