"""Debate service — wraps the core engine for SaaS.

Runs the shared debate cycle (market fetch + AI debate + news) and stores
results to PostgreSQL. This is the most expensive operation (Claude API calls)
and runs ONCE per cycle regardless of user count.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from saas.db.models import DebateResult as DebateResultRow
from saas.db.models import WhaleScanResult

logger = logging.getLogger(__name__)


async def run_debate_cycle(
    session: AsyncSession,
    cycle_id: str,
    market_limit: int = 100,
    concurrency: int = 5,
    news_enabled: bool = True,
    whale_enabled: bool = True,
) -> tuple[int, int]:
    """Run shared debate cycle and store results to DB.

    Returns (num_debates, num_whale_scans).
    """
    # Import core engine (no changes to core code)
    from polymarket_orchestrator.agents import run_debate
    from polymarket_orchestrator.models import DebateResult
    from polymarket_orchestrator.polymarket import PolymarketClient

    # 1. Fetch markets
    logger.info("Cycle %s: fetching markets (limit=%s)...", cycle_id, market_limit)
    client = PolymarketClient()
    markets = client.get_active_markets(limit=market_limit)
    logger.info("Cycle %s: %d markets found.", cycle_id, len(markets))

    if not markets:
        return 0, 0

    # 2. Initialize news aggregator (optional)
    aggregator = None
    if news_enabled:
        try:
            from polymarket_orchestrator.config import settings as cli_settings
            from polymarket_orchestrator.news import NewsAggregator
            aggregator = NewsAggregator(cli_settings)
        except Exception as e:
            logger.warning("News aggregator init failed: %s", e)

    # 3. Debate markets in batches
    num_debates = 0
    for batch_start in range(0, len(markets), concurrency):
        batch = markets[batch_start:batch_start + concurrency]

        # Pre-fetch news for batch
        batch_news: dict[str, list] = {}
        if aggregator:
            try:
                batch_news = await aggregator.get_news_for_batch(batch)
            except Exception as e:
                logger.warning("News fetch failed: %s", e)

        # Run debates concurrently
        async def _debate_one(market):
            try:
                return await run_debate(market, news_articles=batch_news.get(market.id))
            except Exception as e:
                logger.error("Debate failed for '%s': %s", market.question, e)
                return None

        results = await asyncio.gather(*(_debate_one(m) for m in batch))

        # Store results to DB
        for market, result in zip(batch, results):
            if result is None:
                continue

            row = DebateResultRow(
                cycle_id=cycle_id,
                market_id=market.id,
                market_question=market.question,
                market_data=market.model_dump(mode="json"),
                opinions=[op.model_dump(mode="json") for op in result.opinions],
                consensus_probability=result.consensus_probability,
                synthesis_reasoning=result.synthesis_reasoning,
                polymarket_price=market.yes_price,
                news_articles=[],  # Could store news if needed
            )
            session.add(row)
            num_debates += 1

        await session.flush()
        logger.info("Cycle %s: debated %d/%d markets.", cycle_id, num_debates, len(markets))

    # 4. Whale scan (shared)
    num_whale_scans = 0
    if whale_enabled:
        try:
            from polymarket_orchestrator.config import settings as cli_settings
            from polymarket_orchestrator.whale import WhaleTracker

            tracker = WhaleTracker(cli_settings)
            whale_report = await tracker.scan_all()
            await tracker.close()

            # Store whale scan results
            seen_wallets: set[str] = set()
            for ws in whale_report.wallet_stats:
                if ws.address in seen_wallets:
                    continue
                seen_wallets.add(ws.address)
                # Find new trades for this wallet
                wallet_trades = [
                    t.model_dump(mode="json")
                    for t in whale_report.new_trades
                    if t.wallet_address == ws.address
                ]
                row = WhaleScanResult(
                    cycle_id=cycle_id,
                    wallet_address=ws.address,
                    wallet_label=ws.label,
                    wallet_stats=ws.model_dump(mode="json"),
                    new_trades=wallet_trades,
                )
                session.add(row)
                num_whale_scans += 1

            await session.flush()
            logger.info("Cycle %s: scanned %d whale wallets.", cycle_id, num_whale_scans)
        except Exception as e:
            logger.warning("Whale scan failed: %s", e)

    # Cleanup
    if aggregator:
        await aggregator.close()

    return num_debates, num_whale_scans
