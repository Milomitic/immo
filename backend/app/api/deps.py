import secrets
from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Gate for mutating endpoints. No-op when ADMIN_TOKEN is unset (local
    single-user use). It keeps strangers from launching scrapes if the app
    is exposed (tunnel, LAN) — it is not user authentication; for a public
    deployment put the app behind an authenticating reverse proxy."""
    expected = settings.ADMIN_TOKEN
    if not expected:
        return
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Token amministratore mancante o errato")
