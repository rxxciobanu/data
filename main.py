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
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    # Late import so dotenv loads before anything touches settings
    from polymarket_orchestrator.orchestrator import run_analysis

    limit_desc = f"top {args.limit}" if args.limit else "ALL"
    logger.info("=== Polymarket AI Orchestrator === (%s markets, concurrency=%d)", limit_desc, args.concurrency)
    alerts = asyncio.run(run_analysis(market_limit=args.limit, concurrency=args.concurrency))

    if alerts:
        logger.info("--- Summary: %d opportunity(ies) found ---", len(alerts))
        for a in alerts:
            print(
                f"  {a.recommended_side:>3}  {a.divergence_pct:>6}  {a.market.question}"
            )
    else:
        logger.info("No opportunities above threshold. Done.")

    sys.exit(0)


if __name__ == "__main__":
    main()
