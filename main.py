#!/usr/bin/env python3
"""Polymarket AI Orchestrator — CLI entry point.

Fetches active Polymarket prediction markets, runs a multi-agent AI debate
on each market's likely outcome, and emails you when the AI consensus
diverges significantly from Polymarket's current odds.

Usage:
    python main.py
"""
from __future__ import annotations

import asyncio
import logging
import sys


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    # Late import so dotenv loads before anything touches settings
    from polymarket_orchestrator.orchestrator import run_analysis

    logger.info("=== Polymarket AI Orchestrator ===")
    alerts = asyncio.run(run_analysis())

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
