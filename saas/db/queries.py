"""Reusable database query functions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from saas.db.models import (
    ApiKey,
    DebateResult,
    UsageLog,
    User,
    UserAlert,
    UserPreferences,
    WhaleState,
)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, email: str, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    await session.flush()
    # Create default preferences
    prefs = UserPreferences(user_id=user.id)
    session.add(prefs)
    await session.flush()
    return user


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


async def create_api_key(
    session: AsyncSession, user_id: uuid.UUID, key_hash: str, key_prefix: str, label: str = "",
) -> ApiKey:
    key = ApiKey(user_id=user_id, key_hash=key_hash, key_prefix=key_prefix, label=label)
    session.add(key)
    await session.flush()
    return key


async def get_api_keys_by_prefix(session: AsyncSession, prefix: str) -> list[ApiKey]:
    result = await session.execute(
        select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.is_active.is_(True))
    )
    return list(result.scalars().all())


async def get_user_api_keys(session: AsyncSession, user_id: uuid.UUID) -> list[ApiKey]:
    result = await session.execute(
        select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def deactivate_api_key(session: AsyncSession, key_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await session.execute(
        update(ApiKey)
        .where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        .values(is_active=False)
    )
    return result.rowcount > 0


async def touch_api_key(session: AsyncSession, key_id: uuid.UUID) -> None:
    await session.execute(
        update(ApiKey).where(ApiKey.id == key_id).values(last_used=datetime.now(timezone.utc))
    )


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


async def get_preferences(session: AsyncSession, user_id: uuid.UUID) -> UserPreferences | None:
    result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_preferences(session: AsyncSession, user_id: uuid.UUID, **kwargs) -> UserPreferences:
    prefs = await get_preferences(session, user_id)
    if prefs is None:
        prefs = UserPreferences(user_id=user_id, **kwargs)
        session.add(prefs)
    else:
        for k, v in kwargs.items():
            if hasattr(prefs, k):
                setattr(prefs, k, v)
    await session.flush()
    return prefs


# ---------------------------------------------------------------------------
# Debate Results
# ---------------------------------------------------------------------------


async def store_debate_result(session: AsyncSession, **kwargs) -> DebateResult:
    result = DebateResult(**kwargs)
    session.add(result)
    await session.flush()
    return result


async def get_debate_results_by_cycle(session: AsyncSession, cycle_id: str) -> list[DebateResult]:
    result = await session.execute(
        select(DebateResult).where(DebateResult.cycle_id == cycle_id)
    )
    return list(result.scalars().all())


async def get_latest_cycle_id(session: AsyncSession) -> str | None:
    result = await session.execute(
        select(DebateResult.cycle_id)
        .order_by(DebateResult.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_debate_result_by_market(
    session: AsyncSession, market_id: str, cycle_id: str | None = None,
) -> DebateResult | None:
    q = select(DebateResult).where(DebateResult.market_id == market_id)
    if cycle_id:
        q = q.where(DebateResult.cycle_id == cycle_id)
    q = q.order_by(DebateResult.created_at.desc()).limit(1)
    result = await session.execute(q)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# User Alerts
# ---------------------------------------------------------------------------


async def create_user_alert(session: AsyncSession, **kwargs) -> UserAlert:
    alert = UserAlert(**kwargs)
    session.add(alert)
    await session.flush()
    return alert


async def bulk_create_user_alerts(session: AsyncSession, alerts: list[dict]) -> int:
    if not alerts:
        return 0
    session.add_all([UserAlert(**a) for a in alerts])
    await session.flush()
    return len(alerts)


async def get_user_alerts(
    session: AsyncSession,
    user_id: uuid.UUID,
    page: int = 1,
    limit: int = 20,
    cycle_id: str | None = None,
) -> list[UserAlert]:
    q = select(UserAlert).where(UserAlert.user_id == user_id)
    if cycle_id:
        q = q.where(UserAlert.cycle_id == cycle_id)
    q = q.order_by(UserAlert.created_at.desc()).offset((page - 1) * limit).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_user_alert_by_id(
    session: AsyncSession, alert_id: uuid.UUID, user_id: uuid.UUID,
) -> UserAlert | None:
    result = await session.execute(
        select(UserAlert).where(UserAlert.id == alert_id, UserAlert.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_alert_stats(session: AsyncSession, user_id: uuid.UUID) -> dict:
    result = await session.execute(
        select(
            func.count(UserAlert.id),
            func.avg(func.abs(UserAlert.divergence)),
            func.sum(UserAlert.bet_amount),
        ).where(UserAlert.user_id == user_id)
    )
    row = result.one()
    return {
        "total_alerts": row[0] or 0,
        "avg_divergence": float(row[1]) if row[1] else 0.0,
        "total_bet_amount": float(row[2]) if row[2] else 0.0,
    }


async def mark_alerts_notified(
    session: AsyncSession, alert_ids: list[uuid.UUID], channel: str = "email",
) -> None:
    now = datetime.now(timezone.utc)
    await session.execute(
        update(UserAlert)
        .where(UserAlert.id.in_(alert_ids))
        .values(notified=True, notified_at=now, notification_channel=channel)
    )


# ---------------------------------------------------------------------------
# Active Users (for fan-out)
# ---------------------------------------------------------------------------


async def get_active_users_with_prefs(
    session: AsyncSession, offset: int = 0, limit: int = 1000,
) -> list[tuple[User, UserPreferences]]:
    """Fetch active users with preferences in batches for fan-out."""
    result = await session.execute(
        select(User, UserPreferences)
        .join(UserPreferences, User.id == UserPreferences.user_id)
        .where(User.is_active.is_(True), UserPreferences.alert_enabled.is_(True))
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


# ---------------------------------------------------------------------------
# Whale State
# ---------------------------------------------------------------------------


async def get_whale_last_seen(
    session: AsyncSession, user_id: uuid.UUID, address: str,
) -> datetime | None:
    result = await session.execute(
        select(WhaleState.last_seen).where(
            WhaleState.user_id == user_id, WhaleState.address == address,
        )
    )
    return result.scalar_one_or_none()


async def upsert_whale_last_seen(
    session: AsyncSession, user_id: uuid.UUID, address: str, last_seen: datetime,
) -> None:
    stmt = pg_insert(WhaleState).values(
        user_id=user_id, address=address, last_seen=last_seen,
    ).on_conflict_do_update(
        index_elements=["user_id", "address"],
        set_={"last_seen": last_seen},
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# Usage Logging
# ---------------------------------------------------------------------------


async def log_usage(
    session: AsyncSession, user_id: uuid.UUID, event_type: str, metadata: dict | None = None,
) -> None:
    session.add(UsageLog(user_id=user_id, event_type=event_type, metadata_=metadata or {}))
    await session.flush()
