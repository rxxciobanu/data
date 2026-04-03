from __future__ import annotations

import asyncio
import logging

from polymarket_orchestrator.agents import run_debate
from polymarket_orchestrator.config import settings
from polymarket_orchestrator.models import BettingAlert, DebateResult, Market
from polymarket_orchestrator.notifier import send_alert_email
from polymarket_orchestrator.polymarket import PolymarketClient

logger = logging.getLogger(__name__)


async def _debate_market(market: Market) -> DebateResult | None:
    """Run debate on a single market, returning None on failure."""
    try:
        logger.info("Debating: %s", market.question)
        result = await run_debate(market)
        logger.info(
            "  Consensus: %.1f%% (Polymarket: %.1f%%)",
            result.consensus_probability * 100,
            market.yes_price * 100,
        )
        return result
    except Exception as e:
        logger.error("Failed to debate market '%s': %s", market.question, e)
        return None


def _check_divergence(result: DebateResult) -> BettingAlert | None:
    """Check if the AI consensus diverges enough from Polymarket to alert."""
    market = result.market
    poly_prob = market.yes_price
    ai_prob = result.consensus_probability
    divergence = ai_prob - poly_prob

    if abs(divergence) < settings.alert_threshold:
        return None

    # If AI thinks probability is higher than market → bet YES
    # If AI thinks probability is lower than market → bet NO
    recommended_side = "YES" if divergence > 0 else "NO"

    return BettingAlert(
        market=market,
        polymarket_probability=poly_prob,
        ai_probability=ai_prob,
        divergence=divergence,
        recommended_side=recommended_side,
        reasoning=result.synthesis_reasoning,
    )


async def run_analysis(
    market_limit: int | None = None,
    concurrency: int = 5,
) -> list[BettingAlert]:
    """Main orchestration: fetch markets, debate, detect opportunities, notify.

    Args:
        market_limit: Max markets to fetch.  ``None`` means **all** active
            markets on Polymarket (paginated automatically).
        concurrency: How many markets to debate in parallel.  Keeps API
            usage reasonable while still being fast.
    """
    logger.info("Fetching active markets from Polymarket...")
    client = PolymarketClient()
    markets = client.get_active_markets(limit=market_limit)
    logger.info("Found %d markets to analyze.", len(markets))

    if not markets:
        logger.warning("No active markets found.")
        return []

    # Debate markets in batches of `concurrency` for throughput + rate-limit safety
    alerts: list[BettingAlert] = []
    total = len(markets)
    for batch_start in range(0, total, concurrency):
        batch = markets[batch_start : batch_start + concurrency]
        batch_end = min(batch_start + len(batch), total)
        logger.info(
            "Debating batch %d–%d of %d markets...",
            batch_start + 1, batch_end, total,
        )

        results = await asyncio.gather(
            *(_debate_market(m) for m in batch),
            return_exceptions=False,
        )

        for result in results:
            if result is None:
                continue
            alert = _check_divergence(result)
            if alert:
                alerts.append(alert)
                logger.info(
                    "  ** ALERT: %s divergence on '%s' — bet %s",
                    alert.divergence_pct,
                    alert.market.question,
                    alert.recommended_side,
                )

    # Send email if we found opportunities
    if alerts:
        logger.info("Sending email with %d alert(s) out of %d markets analyzed.", len(alerts), total)
        send_alert_email(alerts)
        logger.info("Email sent successfully.")
    else:
        logger.info(
            "No betting opportunities found across %d markets (threshold: %.0f%%).",
            total, settings.alert_threshold * 100,
        )

    return alerts
