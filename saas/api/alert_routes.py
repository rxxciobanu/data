"""Alert endpoints — per-user alert history and latest cycle."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from saas.db.engine import get_db_session
from saas.db.queries import (
    get_latest_cycle_id,
    get_user_alert_by_id,
    get_user_alert_stats,
    get_user_alerts,
)
from saas.deps import CurrentUserID

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AlertResponse(BaseModel):
    id: str
    cycle_id: str
    market_id: str
    market_question: str
    polymarket_probability: float
    ai_probability: float
    divergence: float
    recommended_side: str
    bet_amount: float | None = None
    sizing_details: dict | None = None
    whale_signals: list = []
    notified: bool
    created_at: str


class AlertStatsResponse(BaseModel):
    total_alerts: int
    avg_divergence: float
    total_bet_amount: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    cycle_id: str | None = None,
):
    alerts = await get_user_alerts(session, user_id, page=page, limit=limit, cycle_id=cycle_id)
    return [
        AlertResponse(
            id=str(a.id),
            cycle_id=a.cycle_id,
            market_id=a.market_id,
            market_question=a.market_question,
            polymarket_probability=a.polymarket_probability,
            ai_probability=a.ai_probability,
            divergence=a.divergence,
            recommended_side=a.recommended_side,
            bet_amount=a.bet_amount,
            sizing_details=a.sizing_details,
            whale_signals=a.whale_signals or [],
            notified=a.notified,
            created_at=a.created_at.isoformat(),
        )
        for a in alerts
    ]


@router.get("/latest", response_model=list[AlertResponse])
async def latest_alerts(
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    cycle_id = await get_latest_cycle_id(session)
    if cycle_id is None:
        return []
    alerts = await get_user_alerts(session, user_id, cycle_id=cycle_id, limit=100)
    return [
        AlertResponse(
            id=str(a.id),
            cycle_id=a.cycle_id,
            market_id=a.market_id,
            market_question=a.market_question,
            polymarket_probability=a.polymarket_probability,
            ai_probability=a.ai_probability,
            divergence=a.divergence,
            recommended_side=a.recommended_side,
            bet_amount=a.bet_amount,
            sizing_details=a.sizing_details,
            whale_signals=a.whale_signals or [],
            notified=a.notified,
            created_at=a.created_at.isoformat(),
        )
        for a in alerts
    ]


@router.get("/stats", response_model=AlertStatsResponse)
async def alert_stats(
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    return await get_user_alert_stats(session, user_id)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: uuid.UUID,
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    alert = await get_user_alert_by_id(session, alert_id, user_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return AlertResponse(
        id=str(alert.id),
        cycle_id=alert.cycle_id,
        market_id=alert.market_id,
        market_question=alert.market_question,
        polymarket_probability=alert.polymarket_probability,
        ai_probability=alert.ai_probability,
        divergence=alert.divergence,
        recommended_side=alert.recommended_side,
        bet_amount=alert.bet_amount,
        sizing_details=alert.sizing_details,
        whale_signals=alert.whale_signals or [],
        notified=alert.notified,
        created_at=alert.created_at.isoformat(),
    )
