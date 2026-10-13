"""Saved searches: filter validation, "what's new" counts, e-mail digests."""

import asyncio
import json
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
from urllib.parse import urlencode

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.alert import SearchAlert
from app.schemas.listing import ListingResponse, ListingSearchParams
from app.services.listing_service import search_listings

logger = structlog.get_logger()

# Not part of what a saved search *is*: paging and sorting belong to the
# view, bbox is the map viewport, and the "since" filters are applied from
# the alert's own watermarks. Stripped on save rather than rejected, so the
# frontend can send the /search query string as-is.
_VIEW_KEYS = frozenset({"page", "page_size", "sort", "bbox", "first_seen_after", "price_drop_since"})
_FILTER_KEYS = frozenset(ListingSearchParams.model_fields) - _VIEW_KEYS
_DIGEST_ITEMS = 10


class InvalidFiltersError(ValueError):
    pass


def clean_filters(raw: dict) -> dict:
    """Validated filters worth storing (known keys, non-empty values)."""
    unknown = sorted(k for k in raw if k not in _FILTER_KEYS | _VIEW_KEYS)
    if unknown:
        raise InvalidFiltersError(f"Filtri sconosciuti: {', '.join(unknown)}")
    cleaned = {k: v for k, v in raw.items() if k in _FILTER_KEYS and v not in (None, "")}
    try:
        ListingSearchParams.model_validate(cleaned)
    except ValidationError as e:
        err = e.errors()[0]
        raise InvalidFiltersError(f"{err['loc'][0]}: {err['msg']}") from e
    return cleaned


def alert_filters(alert: SearchAlert) -> dict:
    try:
        data = json.loads(alert.filters or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _since(alert: SearchAlert) -> str:
    return alert.seen_at or alert.created_at


async def _count(db: AsyncSession, alert: SearchAlert, **extra) -> int:
    params = ListingSearchParams.model_validate({**alert_filters(alert), **extra, "page_size": 1})
    return (await search_listings(db, params)).total


async def alert_counts(db: AsyncSession, alert: SearchAlert) -> tuple[int, int, int]:
    """(matching now, first seen since seen_at, price drops since seen_at)."""
    try:
        return (
            await _count(db, alert),
            await _count(db, alert, first_seen_after=_since(alert)),
            await _count(db, alert, price_drop_since=_since(alert)),
        )
    except ValidationError:
        # Stored before a filter changed shape: show it, don't break the list.
        logger.warning("alert_filters_invalid", alert_id=alert.id)
        return 0, 0, 0


# --------------------------------------------------------------- e-mail


def smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.ALERT_EMAIL_TO)


def _search_link(alert: SearchAlert, since: str) -> str:
    query = urlencode({**alert_filters(alert), "first_seen_after": since})
    return f"{settings.FRONTEND_URL}/search?{query}"


def _price(value: float | None) -> str:
    return f"€ {value:,.0f}".replace(",", ".") if value else "Prezzo su richiesta"


def render_digest(sections: list[tuple[SearchAlert, str, int, list[ListingResponse]]]) -> EmailMessage:
    total = sum(count for _, _, count, _ in sections)
    msg = EmailMessage()
    msg["Subject"] = f"Immo: {total} nuovi annunci per le tue ricerche"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER or "immo@localhost"
    msg["To"] = settings.ALERT_EMAIL_TO

    text_parts, html_parts = [], []
    for alert, since, count, items in sections:
        name = alert.name or "Ricerca salvata"
        link = _search_link(alert, since)
        text_parts.append(f"{name}: {count} nuovi\n")
        html_parts.append(f"<h3>{escape(name)} &middot; {count} nuovi</h3><ul>")
        for item in items:
            url = f"{settings.FRONTEND_URL}/listing/{item.id}"
            where = ", ".join(p for p in (item.zone, item.city) if p)
            text_parts.append(f"  - {_price(item.price)} · {item.title} · {where}\n    {url}\n")
            html_parts.append(
                f'<li><a href="{escape(url)}">{escape(item.title)}</a> '
                f"&middot; <b>{_price(item.price)}</b> &middot; {escape(where)}</li>"
            )
        html_parts.append(f'</ul><p><a href="{escape(link)}">Vedi tutti</a></p>')
        text_parts.append(f"  Tutti: {link}\n\n")

    msg.set_content("".join(text_parts))
    msg.add_alternative("".join(html_parts), subtype="html")
    return msg


def _send(msg: EmailMessage) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


async def send_alert_digest() -> int:
    """E-mail what's new for each active saved search since its last digest.

    Meant to run after a scrape job. Watermarks only move once the mail is
    out, so a failed send is retried with the same listings next time.
    Returns how many saved searches had news. No-op without SMTP settings.
    """
    if not smtp_configured():
        return 0
    now = datetime.now(timezone.utc).isoformat()
    async with async_session() as db:
        alerts = (await db.execute(select(SearchAlert).where(SearchAlert.is_active.is_(True)))).scalars().all()
        sections = []
        for alert in alerts:
            since = alert.last_notified_at or alert.created_at
            try:
                params = ListingSearchParams.model_validate({
                    **alert_filters(alert), "first_seen_after": since,
                    "sort": "newest", "page_size": _DIGEST_ITEMS,
                })
            except ValidationError:
                continue
            page = await search_listings(db, params)
            if page.total:
                sections.append((alert, since, page.total, page.items))

        if sections:
            await asyncio.to_thread(_send, render_digest(sections))
            logger.info("alert_digest_sent", alerts=len(sections))
        for alert in alerts:
            alert.last_notified_at = now
        await db.commit()
    return len(sections)
