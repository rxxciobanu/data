"""Celery task: periodic debate cycle.

Fetches markets, runs AI debates, stores results to DB,
then triggers fan-out to generate per-user alerts.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from saas.workers.celery_app import app

logger = logging.getLogger(__name__)


def _generate_cycle_id() -> str:
    """Generate a unique cycle identifier based on current UTC time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@app.task(name="saas.workers.debate_cycle.run_cycle", bind=True, max_retries=2)
def run_cycle(self, market_limit: int | None = None, concurrency: int | None = None):
    """Main debate cycle task — runs every N minutes via Celery Beat.

    1. Fetch markets from Polymarket
    2. Run 3-agent AI debate on each market
    3. Store results to PostgreSQL
    4. Trigger fan_out task
    """
    cycle_id = _generate_cycle_id()
    logger.info("Starting debate cycle %s", cycle_id)

    try:
        num_debates, num_whale_scans = asyncio.get_event_loop().run_until_complete(
            _run_async_cycle(cycle_id, market_limit, concurrency)
        )
    except RuntimeError:
        # No event loop — create one
        loop = asyncio.new_event_loop()
        try:
            num_debates, num_whale_scans = loop.run_until_complete(
                _run_async_cycle(cycle_id, market_limit, concurrency)
            )
        finally:
            loop.close()

    logger.info(
        "Debate cycle %s complete: %d debates, %d whale scans. Triggering fan-out.",
        cycle_id, num_debates, num_whale_scans,
    )

    # Trigger fan-out
    from saas.workers.fan_out import fan_out_alerts

    fan_out_alerts.delay(cycle_id)

    return {"cycle_id": cycle_id, "debates": num_debates, "whale_scans": num_whale_scans}


async def _run_async_cycle(
    cycle_id: str,
    market_limit: int | None = None,
    concurrency: int | None = None,
) -> tuple[int, int]:
    """Async wrapper for the debate cycle."""
    from saas.db.engine import get_session_factory
    from saas.services.debate_service import run_debate_cycle
    from saas.settings import get_settings

    settings = get_settings()
    limit = market_limit or settings.debate_market_limit
    conc = concurrency or settings.debate_concurrency

    factory = get_session_factory()
    async with factory() as session:
        try:
            result = await run_debate_cycle(
                session=session,
                cycle_id=cycle_id,
                market_limit=limit,
                concurrency=conc,
                news_enabled=settings.news_enabled,
                whale_enabled=True,
            )
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
