from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_admin
from app.models.favorite import Favorite
from app.models.listing import Listing
from app.schemas.favorite import FavoriteResponse
from app.services.listing_service import listing_to_response

router = APIRouter(prefix="/favorites", tags=["favorites"])

# listing_to_response needs the listing's sources loaded up front.
_WITH_LISTING = selectinload(Favorite.listing).selectinload(Listing.sources)


def _to_response(fav: Favorite) -> FavoriteResponse:
    return FavoriteResponse(listing=listing_to_response(fav.listing), created_at=fav.created_at)


@router.get("", response_model=list[FavoriteResponse])
async def list_favorites(db: AsyncSession = Depends(get_db)) -> list[FavoriteResponse]:
    """Newest first. Listings that left the market stay in the list
    (``is_active`` false): the user saved them, the UI marks them."""
    rows = await db.execute(
        select(Favorite).options(_WITH_LISTING).order_by(Favorite.created_at.desc(), Favorite.id.desc())
    )
    return [_to_response(f) for f in rows.scalars()]


@router.get("/ids", response_model=list[str])
async def favorite_ids(db: AsyncSession = Depends(get_db)) -> list[str]:
    """Just the saved listing ids — what the hearts on every card need."""
    return list((await db.execute(select(Favorite.listing_id))).scalars())


@router.put(
    "/{listing_id}",
    response_model=FavoriteResponse,
    dependencies=[Depends(require_admin)],
    responses={201: {"description": "Saved"}, 200: {"description": "Already saved"}},
)
async def add_favorite(
    listing_id: str, response: Response, db: AsyncSession = Depends(get_db)
) -> FavoriteResponse:
    """Idempotent save: 201 the first time, 200 when already saved."""
    if await db.get(Listing, listing_id) is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    query = select(Favorite).options(_WITH_LISTING).where(Favorite.listing_id == listing_id)
    fav = (await db.execute(query)).scalar_one_or_none()
    if fav is None:
        db.add(Favorite(listing_id=listing_id))
        try:
            await db.commit()
            response.status_code = 201
        except IntegrityError:  # a concurrent request saved it first
            await db.rollback()
        fav = (await db.execute(query)).scalar_one()
    return _to_response(fav)


@router.delete("/{listing_id}", status_code=204, dependencies=[Depends(require_admin)])
async def remove_favorite(listing_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Idempotent: removing a listing that isn't saved is not an error."""
    await db.execute(delete(Favorite).where(Favorite.listing_id == listing_id))
    await db.commit()
