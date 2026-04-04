#!/usr/bin/env python3
"""Polymarket AI Orchestrator — CLI entry point.

Fetches ALL active Polymarket prediction markets, runs a multi-agent AI
debate on each market's likely outcome, and emails you when the AI consensus
diverges significantly from Polymarket's current odds.

Usage:
    python main.py              # Analyze ALL active markets
    python main.py --limit 20   # Analyze only the top 20 by liquidity
    python main.py --concurrency 10  # Run 10 debates in parallel
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket AI Orchestrator")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max markets to analyze (default: all active markets)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=5,
        help="Number of markets to debate in parallel (default: 5)",
    )
    parser.add_argument(
        "--bankroll", type=float, default=None,
        help="Bankroll in USD for position sizing (overrides BANKROLL env var). "
             "Omit or set to 0 to disable sizing.",
    )
    parser.add_argument(
        "--whale", action="store_true", default=None,
        help="Enable whale wallet tracking (overrides WHALE_ENABLED env var)",
    )
    parser.add_argument(
        "--no-whale", action="store_true", default=None,
        help="Disable whale wallet tracking",
    )
    args = parser.parse_args()

    # Override env vars before importing settings
    import os
    if args.bankroll is not None:
        os.environ["BANKROLL"] = str(args.bankroll)
    if args.whale:
        os.environ["WHALE_ENABLED"] = "true"
    elif args.no_whale:
        os.environ["WHALE_ENABLED"] = "false"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    # Late import so dotenv loads before anything touches settings
    from polymarket_orchestrator.config import settings
    from polymarket_orchestrator.orchestrator import run_analysis

    limit_desc = f"top {args.limit}" if args.limit else "ALL"
    bankroll_desc = f", bankroll=${settings.bankroll:,.0f}" if settings.bankroll > 0 else ""
    logger.info(
        "=== Polymarket AI Orchestrator === (%s markets, concurrency=%d%s)",
        limit_desc, args.concurrency, bankroll_desc,
    )
    alerts = asyncio.run(run_analysis(market_limit=args.limit, concurrency=args.concurrency))

    if alerts:
        logger.info("--- Summary: %d opportunity(ies) found ---", len(alerts))
        for a in alerts:
            size_str = ""
            if a.sizing and a.sizing.bet_amount > 0:
                size_str = f"  ${a.sizing.bet_amount:>8,.0f} ({a.sizing.bet_pct_bankroll:.1%})"
                if a.sizing.capped:
                    size_str += f" [{a.sizing.cap_reason}]"
            print(
                f"  {a.recommended_side:>3}  {a.divergence_pct:>6}{size_str}  {a.market.question}"
            )

        # Total exposure footer
        sized = [a for a in alerts if a.sizing and a.sizing.bet_amount > 0]
        if sized:
            total = sum(a.sizing.bet_amount for a in sized)
            print(f"\n  Total exposure: ${total:,.2f} / ${settings.bankroll:,.0f} "
                  f"({total / settings.bankroll:.1%} of bankroll)")
    else:
        logger.info("No opportunities above threshold. Done.")

    sys.exit(0)


if __name__ == "__main__":
    main()
