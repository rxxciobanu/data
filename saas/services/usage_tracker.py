"""Usage tracking for future billing/analytics."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from saas.db.queries import log_usage

logger = logging.getLogger(__name__)


async def track_alert_generated(session: AsyncSession, user_id: uuid.UUID, market_id: str) -> None:
    await log_usage(session, user_id, "alert_generated", {"market_id": market_id})


async def track_email_sent(session: AsyncSession, user_id: uuid.UUID, alert_count: int) -> None:
    await log_usage(session, user_id, "email_sent", {"alert_count": alert_count})


async def track_api_call(session: AsyncSession, user_id: uuid.UUID, endpoint: str) -> None:
    await log_usage(session, user_id, "api_call", {"endpoint": endpoint})
