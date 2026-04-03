#!/usr/bin/env python3
"""Live test — feeds real Polymarket data (scraped via web search) into the
agent debate pipeline and runs the full orchestration end-to-end.

Usage:
    python test_live.py

Requires: ANTHROPIC_API_KEY environment variable.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from polymarket_orchestrator.agents import run_debate
from polymarket_orchestrator.config import settings
from polymarket_orchestrator.models import BettingAlert, Market, Token
from polymarket_orchestrator.notifier import _build_email_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Real Polymarket data gathered via web search on 2026-04-03
# -----------------------------------------------------------------------
LIVE_MARKETS = [
    Market(
        id="us-recession-2026",
        question="US recession by end of 2026?",
        description=(
            "This market resolves YES if the NBER officially declares a US recession "
            "that begins on or before December 31, 2026. Current economic indicators: "
            "unemployment near 4.6%, Sahm rule indicator at 0.3% (below 0.5% trigger), "
            "steepening yield curve. Recent Iran tensions briefly spiked Yes odds above 40%."
        ),
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="recession-yes", outcome="Yes", price=0.35),
            Token(token_id="recession-no", outcome="No", price=0.645),
        ],
        volume=12_000_000,
        liquidity=800_000,
        end_date="2026-12-31",
    ),
    Market(
        id="balance-of-power-2026",
        question="Balance of Power: 2026 Midterms — Democrats Sweep?",
        description=(
            "Resolves YES if Democrats control both the House and Senate after the "
            "2026 midterm elections (Nov 3, 2026). Current polling: Democrats favored "
            "in House at 86%, Senate is closer. 'Democrats Sweep' leads at 51%, "
            "'R Senate, D House' at 36%. $4.4M traded."
        ),
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="dem-sweep-yes", outcome="Yes", price=0.51),
            Token(token_id="dem-sweep-no", outcome="No", price=0.49),
        ],
        volume=4_400_000,
        liquidity=500_000,
        end_date="2026-11-03",
    ),
    Market(
        id="dem-nominee-2028",
        question="Will Gavin Newsom be the Democratic Presidential Nominee in 2028?",
        description=(
            "Resolves YES if Gavin Newsom wins the Democratic nomination for the 2028 "
            "presidential election. Currently leads at 25%, followed by AOC at 8%. "
            "Recent CA primary polls show Newsom with double-digit lead over Kamala Harris "
            "among state Democrats. Term-limited as governor. $968M total volume."
        ),
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="newsom-yes", outcome="Yes", price=0.25),
            Token(token_id="newsom-no", outcome="No", price=0.75),
        ],
        volume=968_000_000,
        liquidity=5_000_000,
        end_date="2028-08-31",
    ),
    Market(
        id="trump-china-visit",
        question="Will Trump visit China by June 30, 2026?",
        description=(
            "Resolves YES if Donald Trump makes an official visit to China on or before "
            "June 30, 2026. Originally planned for March 31-April 2, postponed and "
            "rescheduled for May 14-15. White House signals Middle East conflict may "
            "resolve in 4-6 weeks. $9M volume, $688K traded today."
        ),
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="trump-china-yes", outcome="Yes", price=0.83),
            Token(token_id="trump-china-no", outcome="No", price=0.17),
        ],
        volume=9_000_000,
        liquidity=600_000,
        end_date="2026-06-30",
    ),
    Market(
        id="btc-90k-2026",
        question="Will Bitcoin hit $90,000 in 2026?",
        description=(
            "Resolves YES if Bitcoin (BTC/USD) reaches or exceeds $90,000 at any point "
            "before January 1, 2027. Current BTC price around $83-85k. Market currently "
            "prices this at ~100%. $28.8M traded. All-time high market shows 14% chance "
            "of new ATH by end of 2026."
        ),
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="btc-90k-yes", outcome="Yes", price=0.95),
            Token(token_id="btc-90k-no", outcome="No", price=0.05),
        ],
        volume=28_800_000,
        liquidity=1_500_000,
        end_date="2027-01-01",
    ),
    Market(
        id="us-tariff-china",
        question="US tariff rate on China stays at 5-15% on April 30?",
        description=(
            "Resolves YES if the effective US tariff rate on Chinese imports is between "
            "5% and 15% on April 30, 2026. Currently at 99% YES. Trump-Xi summit "
            "rescheduled for May 14-15. Trade war tensions have eased significantly "
            "with bilateral negotiations ongoing."
        ),
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="tariff-yes", outcome="Yes", price=0.99),
            Token(token_id="tariff-no", outcome="No", price=0.01),
        ],
        volume=3_500_000,
        liquidity=200_000,
        end_date="2026-04-30",
    ),
]


async def run_test() -> None:
    logger.info("=" * 60)
    logger.info("  POLYMARKET AI ORCHESTRATOR — LIVE TEST")
    logger.info("  Using real Polymarket data from 2026-04-03")
    logger.info("=" * 60)
    logger.info("")

    threshold = settings.alert_threshold
    alerts: list[BettingAlert] = []
    debate_summaries: list[str] = []

    for market in LIVE_MARKETS:
        logger.info("─" * 50)
        logger.info("MARKET: %s", market.question)
        logger.info("  Polymarket YES price: %.1f%%", market.yes_price * 100)
        logger.info("  Running 4-agent debate (Bull, Bear, Analyst → Synthesizer)...")

        result = await run_debate(market)

        summary = []
        for op in result.opinions:
            logger.info(
                "    %s: %.1f%% (%s confidence) — %s",
                op.agent_name,
                op.probability * 100,
                op.confidence,
                op.reasoning[:80] + "...",
            )
            summary.append(f"  {op.agent_name}: {op.probability:.1%} ({op.confidence})")

        logger.info(
            "  CONSENSUS: %.1f%% (Polymarket: %.1f%%, Δ = %+.1f%%)",
            result.consensus_probability * 100,
            market.yes_price * 100,
            (result.consensus_probability - market.yes_price) * 100,
        )

        debate_summaries.append(
            f"\n{'─'*50}\n"
            f"Market: {market.question}\n"
            + "\n".join(summary)
            + f"\n  Synthesizer: {result.consensus_probability:.1%}\n"
            f"  Polymarket:  {market.yes_price:.1%}\n"
            f"  Divergence:  {result.consensus_probability - market.yes_price:+.1%}"
        )

        divergence = result.consensus_probability - market.yes_price
        if abs(divergence) >= threshold:
            side = "YES" if divergence > 0 else "NO"
            alert = BettingAlert(
                market=market,
                polymarket_probability=market.yes_price,
                ai_probability=result.consensus_probability,
                divergence=divergence,
                recommended_side=side,
                reasoning=result.synthesis_reasoning,
            )
            alerts.append(alert)
            logger.info("  *** ALERT: Bet %s (divergence %.1f%%) ***", side, abs(divergence) * 100)
        else:
            logger.info("  No opportunity (below %.0f%% threshold)", threshold * 100)

    # Print full summary
    print("\n\n" + "=" * 60)
    print("  DEBATE RESULTS SUMMARY")
    print("=" * 60)
    for s in debate_summaries:
        print(s)

    print("\n" + "=" * 60)
    print(f"  BETTING ALERTS ({len(alerts)} found)")
    print("=" * 60)
    if alerts:
        for a in alerts:
            print(f"\n  {'🟢' if a.recommended_side == 'YES' else '🔴'} {a.market.question}")
            print(f"     Bet: {a.recommended_side}")
            print(f"     Polymarket: {a.polymarket_probability:.1%}")
            print(f"     AI Says:    {a.ai_probability:.1%}")
            print(f"     Edge:       {a.divergence_pct}")

        # Generate email preview
        html = _build_email_html(alerts)
        with open("/home/user/data/alert_email_preview.html", "w") as f:
            f.write(html)
        print(f"\n  Email preview saved to: alert_email_preview.html ({len(html)} chars)")
    else:
        print("\n  No opportunities found above threshold.")

    print()


def main() -> None:
    if not settings.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Set it in .env or environment.")
        sys.exit(1)
    asyncio.run(run_test())


if __name__ == "__main__":
    main()
