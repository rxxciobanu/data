from __future__ import annotations

import asyncio
import logging

from polymarket_orchestrator.agents import run_debate
from polymarket_orchestrator.config import settings
from polymarket_orchestrator.models import BettingAlert, DebateResult, Market
from polymarket_orchestrator.notifier import send_alert_email
from polymarket_orchestrator.polymarket import PolymarketClient
from polymarket_orchestrator.sizing import compute_bet_size

logger = logging.getLogger(__name__)


async def _debate_market(market: Market, news_articles: list | None = None) -> DebateResult | None:
    """Run debate on a single market, returning None on failure."""
    try:
        logger.info("Debating: %s", market.question)
        result = await run_debate(market, news_articles=news_articles)
        logger.info(
            "  Consensus: %.1f%% (Polymarket: %.1f%%)",
            result.consensus_probability * 100,
            market.yes_price * 100,
        )
        return result
    except Exception as e:
        logger.error("Failed to debate market '%s': %s", market.question, e)
        return None


def _check_divergence(
    result: DebateResult,
    current_exposure: float = 0.0,
) -> BettingAlert | None:
    """Check if the AI consensus diverges enough from Polymarket to alert."""
    market = result.market
    poly_prob = market.yes_price
    ai_prob = result.consensus_probability
    divergence = ai_prob - poly_prob

    if abs(divergence) < settings.alert_threshold:
        return None

    recommended_side = "YES" if divergence > 0 else "NO"

    alert = BettingAlert(
        market=market,
        polymarket_probability=poly_prob,
        ai_probability=ai_prob,
        divergence=divergence,
        recommended_side=recommended_side,
        reasoning=result.synthesis_reasoning,
    )

    # Position sizing (only when bankroll is configured)
    if settings.bankroll > 0:
        if not market.price_is_live:
            logger.warning(
                "Skipping sizing for '%s' — price data is stale (CLOB enrichment failed).",
                market.question,
            )
        else:
            alert.sizing = compute_bet_size(
                ai_prob=ai_prob,
                market_prob=poly_prob,
                side=recommended_side,
                opinions=result.opinions,
                market=market,
                bankroll=settings.bankroll,
                kelly_fraction_setting=settings.kelly_fraction,
                max_bet_pct=settings.max_bet_pct,
                max_exposure=settings.bankroll * settings.max_total_exposure,
                current_exposure=current_exposure,
                min_bet_size=settings.min_bet_size,
            )

    return alert


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

    # Initialize news aggregator (graceful degradation if unavailable)
    aggregator = None
    if settings.news_enabled:
        try:
            from polymarket_orchestrator.news import NewsAggregator
            aggregator = NewsAggregator(settings)
        except Exception as e:
            logger.warning("News aggregator init failed: %s. Continuing without news.", e)

    # Whale tracker (graceful degradation if unavailable)
    whale_report = None
    if settings.whale_enabled:
        try:
            from polymarket_orchestrator.whale import WhaleTracker
            tracker = WhaleTracker(settings)
            whale_report = await tracker.scan_all()
            await tracker.close()
            logger.info(
                "Whale scan: %d new trades, %d alerts.",
                len(whale_report.new_trades), len(whale_report.alerts),
            )
        except Exception as e:
            logger.warning("Whale tracking failed: %s. Continuing without whale data.", e)

    # Debate markets in batches of `concurrency` for throughput + rate-limit safety
    alerts: list[BettingAlert] = []
    current_exposure = 0.0  # Tracks cumulative bet amounts for portfolio cap
    total = len(markets)
    for batch_start in range(0, total, concurrency):
        batch = markets[batch_start : batch_start + concurrency]
        batch_end = min(batch_start + len(batch), total)
        logger.info(
            "Debating batch %d–%d of %d markets...",
            batch_start + 1, batch_end, total,
        )

        # Pre-fetch news for the entire batch
        batch_news: dict[str, list] = {}
        if aggregator:
            try:
                batch_news = await aggregator.get_news_for_batch(batch)
            except Exception as e:
                logger.warning("News fetch failed for batch: %s", e)

        results = await asyncio.gather(
            *(_debate_market(m, news_articles=batch_news.get(m.id))
              for m in batch),
            return_exceptions=False,
        )

        for result in results:
            if result is None:
                continue
            alert = _check_divergence(result, current_exposure)
            if alert:
                if alert.sizing and alert.sizing.bet_amount > 0:
                    current_exposure += alert.sizing.bet_amount
                alerts.append(alert)
                size_str = ""
                if alert.sizing:
                    size_str = f" | bet ${alert.sizing.bet_amount:,.0f} ({alert.sizing.bet_pct_bankroll:.1%})"
                    if alert.sizing.capped:
                        size_str += f" [{alert.sizing.cap_reason}]"
                logger.info(
                    "  ** ALERT: %s divergence on '%s' — bet %s%s",
                    alert.divergence_pct,
                    alert.market.question,
                    alert.recommended_side,
                    size_str,
                )

    # Cleanup news aggregator
    if aggregator:
        await aggregator.close()

    # Cross-reference whale signals with AI alerts.
    # Whale trades use condition_id (token-level) while Market uses id (market-level).
    # Match via token IDs: build a mapping from each token_id → market alert.
    if whale_report and whale_report.alerts:
        # Build lookup: token_id → alert index (a market has multiple tokens)
        token_to_alert: dict[str, int] = {}
        for i, alert in enumerate(alerts):
            for tok in alert.market.tokens:
                token_to_alert[tok.token_id] = i

        # Also try matching by market slug (whale trades have market_slug)
        slug_to_alert: dict[str, int] = {}
        for i, alert in enumerate(alerts):
            # Derive slug from market id (Gamma API ids are often slug-like)
            slug_to_alert[alert.market.id] = i

        matched_indices: set[int] = set()
        for wa in whale_report.alerts:
            idx = token_to_alert.get(wa.trade.condition_id)
            if idx is None and wa.trade.market_slug:
                idx = slug_to_alert.get(wa.trade.market_slug)
            if idx is not None:
                wa.overlaps_ai_alert = True
                alerts[idx].whale_signals.append(wa)
                matched_indices.add(idx)

    # Send email if we found opportunities (AI alerts or whale alerts)
    has_whale_alerts = whale_report and whale_report.alerts
    if alerts or has_whale_alerts:
        logger.info(
            "Sending email with %d AI alert(s) and %d whale alert(s).",
            len(alerts), len(whale_report.alerts) if whale_report else 0,
        )
        send_alert_email(alerts, whale_report=whale_report)
        logger.info("Email sent successfully.")
    else:
        logger.info(
            "No betting opportunities found across %d markets (threshold: %.0f%%).",
            total, settings.alert_threshold * 100,
        )

    return alerts
