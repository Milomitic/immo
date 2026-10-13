import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.models.alert import SearchAlert
from app.schemas.alert import AlertCreate, AlertResponse, AlertUpdate
from app.services.alert_service import (
    InvalidFiltersError,
    alert_counts,
    alert_filters,
    clean_filters,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


async def _response(db: AsyncSession, alert: SearchAlert) -> AlertResponse:
    total, new, drops = await alert_counts(db, alert)
    return AlertResponse(
        id=alert.id,
        name=alert.name or "Ricerca salvata",
        filters=alert_filters(alert),
        is_active=alert.is_active,
        created_at=alert.created_at,
        seen_at=alert.seen_at,
        last_notified_at=alert.last_notified_at,
        total=total,
        new_count=new,
        price_drop_count=drops,
    )


async def _get_or_404(db: AsyncSession, alert_id: str) -> SearchAlert:
    alert = await db.get(SearchAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Ricerca salvata non trovata")
    return alert


@router.get("", response_model=list[AlertResponse])
async def list_alerts(db: AsyncSession = Depends(get_db)) -> list[AlertResponse]:
    rows = await db.execute(select(SearchAlert).order_by(SearchAlert.created_at.desc()))
    return [await _response(db, alert) for alert in rows.scalars()]


@router.post("", response_model=AlertResponse, status_code=201, dependencies=[Depends(require_admin)])
async def create_alert(body: AlertCreate, db: AsyncSession = Depends(get_db)) -> AlertResponse:
    try:
        filters = clean_filters(body.filters)
    except InvalidFiltersError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    alert = SearchAlert(name=body.name.strip(), filters=json.dumps(filters, sort_keys=True))
    db.add(alert)
    await db.commit()
    return await _response(db, alert)


@router.patch("/{alert_id}", response_model=AlertResponse, dependencies=[Depends(require_admin)])
async def update_alert(alert_id: str, body: AlertUpdate, db: AsyncSession = Depends(get_db)) -> AlertResponse:
    alert = await _get_or_404(db, alert_id)
    if body.name is not None:
        alert.name = body.name.strip()
    if body.is_active is not None:
        alert.is_active = body.is_active
    await db.commit()
    return await _response(db, alert)


@router.post("/{alert_id}/seen", response_model=AlertResponse, dependencies=[Depends(require_admin)])
async def mark_alert_seen(alert_id: str, db: AsyncSession = Depends(get_db)) -> AlertResponse:
    """Move the "new since" watermark to now."""
    alert = await _get_or_404(db, alert_id)
    alert.seen_at = datetime.now(timezone.utc).isoformat()
    await db.commit()
    return await _response(db, alert)


@router.delete("/{alert_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_alert(alert_id: str, db: AsyncSession = Depends(get_db)) -> None:
    await db.execute(delete(SearchAlert).where(SearchAlert.id == alert_id))
    await db.commit()
