"""Market endpoints — read-only, shared debate data."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from saas.db.engine import get_db_session
from saas.db.models import DebateResult
from saas.db.queries import get_debate_result_by_market, get_latest_cycle_id
from saas.deps import CurrentUserID

router = APIRouter(prefix="/markets", tags=["markets"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MarketSummary(BaseModel):
    market_id: str
    market_question: str
    polymarket_price: float
    consensus_probability: float
    divergence: float
    cycle_id: str
    created_at: str


class MarketDebateDetail(BaseModel):
    market_id: str
    market_question: str
    market_data: dict
    polymarket_price: float
    consensus_probability: float
    opinions: list
    synthesis_reasoning: str | None = None
    news_articles: list = []
    cycle_id: str
    created_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[MarketSummary])
async def list_markets(
    _user_id: CurrentUserID,  # Auth required but not user-specific
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    cycle_id = await get_latest_cycle_id(session)
    if cycle_id is None:
        return []

    result = await session.execute(
        select(DebateResult)
        .where(DebateResult.cycle_id == cycle_id)
        .order_by(func.abs(DebateResult.consensus_probability - DebateResult.polymarket_price).desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    debates = result.scalars().all()
    return [
        MarketSummary(
            market_id=d.market_id,
            market_question=d.market_question,
            polymarket_price=d.polymarket_price,
            consensus_probability=d.consensus_probability,
            divergence=d.consensus_probability - d.polymarket_price,
            cycle_id=d.cycle_id,
            created_at=d.created_at.isoformat(),
        )
        for d in debates
    ]


@router.get("/{market_id}", response_model=MarketSummary)
async def get_market(
    market_id: str,
    _user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    debate = await get_debate_result_by_market(session, market_id)
    if debate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found")
    return MarketSummary(
        market_id=debate.market_id,
        market_question=debate.market_question,
        polymarket_price=debate.polymarket_price,
        consensus_probability=debate.consensus_probability,
        divergence=debate.consensus_probability - debate.polymarket_price,
        cycle_id=debate.cycle_id,
        created_at=debate.created_at.isoformat(),
    )


@router.get("/{market_id}/debate", response_model=MarketDebateDetail)
async def get_market_debate(
    market_id: str,
    _user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    debate = await get_debate_result_by_market(session, market_id)
    if debate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market debate not found")
    return MarketDebateDetail(
        market_id=debate.market_id,
        market_question=debate.market_question,
        market_data=debate.market_data,
        polymarket_price=debate.polymarket_price,
        consensus_probability=debate.consensus_probability,
        opinions=debate.opinions,
        synthesis_reasoning=debate.synthesis_reasoning,
        news_articles=debate.news_articles or [],
        cycle_id=debate.cycle_id,
        created_at=debate.created_at.isoformat(),
    )
