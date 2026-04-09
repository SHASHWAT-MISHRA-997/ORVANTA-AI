"""
ORVANTA Cloud - Watchlists API Routes
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org
from app.db.database import get_db
from app.schemas.watchlist import WatchlistCreate, WatchlistResponse
from app.services.watchlist_service import create_watchlist, delete_watchlist, list_watchlists

router = APIRouter(prefix="/watchlists", tags=["Watchlists"])


@router.get("", response_model=list[WatchlistResponse])
async def get_watchlists(
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org, membership = org_context
    return await list_watchlists(org.id, db)


@router.post("", response_model=WatchlistResponse, status_code=201)
async def create_saved_watchlist(
    payload: WatchlistCreate,
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org, membership = org_context
    try:
        return await create_watchlist(org.id, payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{watchlist_id}")
async def remove_watchlist(
    watchlist_id: UUID,
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org, membership = org_context
    try:
        await delete_watchlist(watchlist_id, org.id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"message": "Watchlist deleted successfully"}
