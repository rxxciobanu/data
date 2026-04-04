"""Whale tracking endpoints — per-user config and signals."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saas.db.engine import get_db_session
from saas.db.models import WhaleScanResult
from saas.db.queries import get_latest_cycle_id, get_preferences, update_preferences
from saas.deps import CurrentUserID

router = APIRouter(prefix="/whales", tags=["whales"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class WhaleConfig(BaseModel):
    whale_enabled: bool
    whale_min_trade_size: float
    whale_extra_wallets: list = []


class WhaleConfigUpdate(BaseModel):
    whale_enabled: bool | None = None
    whale_min_trade_size: float | None = Field(None, ge=0)
    whale_extra_wallets: list | None = None


class WhaleSignalResponse(BaseModel):
    wallet_address: str
    wallet_label: str | None = None
    wallet_stats: dict = {}
    new_trades: list = []
    cycle_id: str
    created_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/config", response_model=WhaleConfig)
async def get_whale_config(
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    prefs = await get_preferences(session, user_id)
    if prefs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return WhaleConfig(
        whale_enabled=prefs.whale_enabled,
        whale_min_trade_size=prefs.whale_min_trade_size,
        whale_extra_wallets=prefs.whale_extra_wallets or [],
    )


@router.put("/config", response_model=WhaleConfig)
async def update_whale_config(
    body: WhaleConfigUpdate,
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    prefs = await update_preferences(session, user_id, **updates)
    return WhaleConfig(
        whale_enabled=prefs.whale_enabled,
        whale_min_trade_size=prefs.whale_min_trade_size,
        whale_extra_wallets=prefs.whale_extra_wallets or [],
    )


@router.get("/signals", response_model=list[WhaleSignalResponse])
async def get_whale_signals(
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    cycle_id = await get_latest_cycle_id(session)
    if cycle_id is None:
        return []

    result = await session.execute(
        select(WhaleScanResult)
        .where(WhaleScanResult.cycle_id == cycle_id)
        .order_by(WhaleScanResult.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    scans = result.scalars().all()
    return [
        WhaleSignalResponse(
            wallet_address=s.wallet_address,
            wallet_label=s.wallet_label,
            wallet_stats=s.wallet_stats,
            new_trades=s.new_trades,
            cycle_id=s.cycle_id,
            created_at=s.created_at.isoformat(),
        )
        for s in scans
    ]


@router.get("/leaderboard", response_model=list[WhaleSignalResponse])
async def get_whale_leaderboard(
    _user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    """Current whale leaderboard from the latest cycle (shared data)."""
    cycle_id = await get_latest_cycle_id(session)
    if cycle_id is None:
        return []

    result = await session.execute(
        select(WhaleScanResult)
        .where(WhaleScanResult.cycle_id == cycle_id)
        .order_by(WhaleScanResult.created_at.desc())
        .limit(50)
    )
    scans = result.scalars().all()
    return [
        WhaleSignalResponse(
            wallet_address=s.wallet_address,
            wallet_label=s.wallet_label,
            wallet_stats=s.wallet_stats,
            new_trades=s.new_trades,
            cycle_id=s.cycle_id,
            created_at=s.created_at.isoformat(),
        )
        for s in scans
    ]
