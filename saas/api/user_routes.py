"""User profile and preferences endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from saas.db.engine import get_db_session
from saas.db.queries import get_preferences, get_user_by_id, update_preferences
from saas.deps import CurrentUserID

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserProfile(BaseModel):
    id: str
    email: str
    is_active: bool
    is_verified: bool
    created_at: str


class PreferencesResponse(BaseModel):
    alert_threshold: float
    alert_enabled: bool
    bankroll: float
    kelly_fraction: float
    max_bet_pct: float
    max_total_exposure: float
    min_bet_size: float
    notification_email: str | None = None
    webhook_url: str | None = None
    telegram_chat_id: str | None = None
    whale_enabled: bool
    whale_min_trade_size: float
    whale_extra_wallets: list = []


class PreferencesUpdate(BaseModel):
    alert_threshold: float | None = Field(None, ge=0, le=1)
    alert_enabled: bool | None = None
    bankroll: float | None = Field(None, ge=0)
    kelly_fraction: float | None = Field(None, ge=0.01, le=1)
    max_bet_pct: float | None = Field(None, ge=0.01, le=1)
    max_total_exposure: float | None = Field(None, ge=0.01, le=1)
    min_bet_size: float | None = Field(None, ge=0)
    notification_email: str | None = None
    webhook_url: str | None = None
    telegram_chat_id: str | None = None
    whale_enabled: bool | None = None
    whale_min_trade_size: float | None = Field(None, ge=0)
    whale_extra_wallets: list | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/me", response_model=UserProfile)
async def get_profile(
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return UserProfile(
        id=str(user.id),
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at.isoformat(),
    )


@router.get("/me/preferences", response_model=PreferencesResponse)
async def get_prefs(
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    prefs = await get_preferences(session, user_id)
    if prefs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preferences not found")
    return PreferencesResponse(
        alert_threshold=prefs.alert_threshold,
        alert_enabled=prefs.alert_enabled,
        bankroll=prefs.bankroll,
        kelly_fraction=prefs.kelly_fraction,
        max_bet_pct=prefs.max_bet_pct,
        max_total_exposure=prefs.max_total_exposure,
        min_bet_size=prefs.min_bet_size,
        notification_email=prefs.notification_email,
        webhook_url=prefs.webhook_url,
        telegram_chat_id=prefs.telegram_chat_id,
        whale_enabled=prefs.whale_enabled,
        whale_min_trade_size=prefs.whale_min_trade_size,
        whale_extra_wallets=prefs.whale_extra_wallets or [],
    )


@router.put("/me/preferences", response_model=PreferencesResponse)
async def update_prefs(
    body: PreferencesUpdate,
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    # Only update fields that were explicitly set
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    prefs = await update_preferences(session, user_id, **updates)
    return PreferencesResponse(
        alert_threshold=prefs.alert_threshold,
        alert_enabled=prefs.alert_enabled,
        bankroll=prefs.bankroll,
        kelly_fraction=prefs.kelly_fraction,
        max_bet_pct=prefs.max_bet_pct,
        max_total_exposure=prefs.max_total_exposure,
        min_bet_size=prefs.min_bet_size,
        notification_email=prefs.notification_email,
        webhook_url=prefs.webhook_url,
        telegram_chat_id=prefs.telegram_chat_id,
        whale_enabled=prefs.whale_enabled,
        whale_min_trade_size=prefs.whale_min_trade_size,
        whale_extra_wallets=prefs.whale_extra_wallets or [],
    )
