"""Celery task: fan-out alerts to all users.

After a debate cycle completes, this task iterates over all active users,
applies per-user thresholds and Kelly sizing, and writes user_alerts to DB.
Then triggers per-user notification tasks.

Performance: 10k users × 100 debate results = pure math, completes in seconds.
"""
from __future__ import annotations

import asyncio
import logging

from saas.workers.celery_app import app

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000  # Process users in batches


@app.task(name="saas.workers.fan_out.fan_out_alerts", bind=True)
def fan_out_alerts(self, cycle_id: str):
    """Fan out debate results to all active users."""
    logger.info("Fan-out starting for cycle %s", cycle_id)

    try:
        total_alerts = asyncio.get_event_loop().run_until_complete(
            _async_fan_out(cycle_id)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            total_alerts = loop.run_until_complete(_async_fan_out(cycle_id))
        finally:
            loop.close()

    logger.info("Fan-out complete for cycle %s: %d total alerts generated.", cycle_id, total_alerts)
    return {"cycle_id": cycle_id, "total_alerts": total_alerts}


async def _async_fan_out(cycle_id: str) -> int:
    """Async fan-out: load debate results, iterate users, generate alerts."""
    from saas.db.engine import get_session_factory
    from saas.db.models import UserAlert
    from saas.db.queries import get_active_users_with_prefs, get_debate_results_by_cycle
    from saas.services.alert_service import generate_alerts_for_user

    factory = get_session_factory()
    total_alerts = 0

    async with factory() as session:
        # Load shared debate results (same for all users)
        debate_results = await get_debate_results_by_cycle(session, cycle_id)
        if not debate_results:
            logger.warning("No debate results for cycle %s", cycle_id)
            return 0

        logger.info("Fan-out: %d debate results for cycle %s", len(debate_results), cycle_id)

        # Process users in batches
        offset = 0
        user_ids_to_notify: list[str] = []

        while True:
            users_with_prefs = await get_active_users_with_prefs(session, offset=offset, limit=BATCH_SIZE)
            if not users_with_prefs:
                break

            for user, prefs in users_with_prefs:
                alerts = generate_alerts_for_user(
                    user_id=user.id,
                    prefs=prefs,
                    debate_results=debate_results,
                )

                if alerts:
                    for a in alerts:
                        row = UserAlert(
                            user_id=a.user_id,
                            debate_result_id=a.debate_result_id,
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
                        )
                        session.add(row)
                    total_alerts += len(alerts)
                    user_ids_to_notify.append(str(user.id))

            await session.flush()
            offset += BATCH_SIZE

            logger.info(
                "Fan-out: processed %d users, %d alerts so far.",
                offset, total_alerts,
            )

        await session.commit()

    # Trigger notification tasks for users with new alerts
    from saas.workers.notify import send_user_notification

    for uid in user_ids_to_notify:
        send_user_notification.delay(uid, cycle_id)

    return total_alerts
