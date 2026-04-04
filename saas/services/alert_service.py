"""Alert service — per-user alert generation from shared debate results.

This is the fan-out: for each user, apply their threshold and Kelly sizing
to the shared debate results. Pure math, no LLM calls. Handles 10k users
in seconds.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from saas.db.models import DebateResult, UserPreferences

logger = logging.getLogger(__name__)


@dataclass
class GeneratedAlert:
    """Alert ready to be written to DB."""
    user_id: uuid.UUID
    debate_result_id: uuid.UUID
    cycle_id: str
    market_id: str
    market_question: str
    polymarket_probability: float
    ai_probability: float
    divergence: float
    recommended_side: str
    bet_amount: float | None = None
    sizing_details: dict | None = None
    whale_signals: list | None = None


def generate_alerts_for_user(
    user_id: uuid.UUID,
    prefs: UserPreferences,
    debate_results: list[DebateResult],
    whale_scan_data: dict | None = None,
) -> list[GeneratedAlert]:
    """Apply user's threshold + Kelly sizing to shared debate results.

    Args:
        user_id: The user's ID.
        prefs: User preferences (threshold, bankroll, Kelly params).
        debate_results: List of DebateResult rows from the current cycle.
        whale_scan_data: Optional dict of whale signals per market.

    Returns:
        List of GeneratedAlert objects ready for DB insertion.
    """
    alerts: list[GeneratedAlert] = []
    current_exposure = 0.0

    for dr in debate_results:
        poly_prob = dr.polymarket_price
        ai_prob = dr.consensus_probability
        divergence = ai_prob - poly_prob

        # Apply user's threshold
        if abs(divergence) < prefs.alert_threshold:
            continue

        recommended_side = "YES" if divergence > 0 else "NO"

        # Position sizing (only when bankroll is configured)
        bet_amount = None
        sizing_details = None

        if prefs.bankroll > 0:
            try:
                from polymarket_orchestrator.sizing import compute_bet_size
                from polymarket_orchestrator.models import Market, Token

                # Reconstruct market from stored data for sizing
                market_data = dr.market_data
                market = Market(**market_data)

                sizing = compute_bet_size(
                    ai_prob=ai_prob,
                    market_prob=poly_prob,
                    side=recommended_side,
                    opinions=[],  # Opinions stored but not needed for sizing recalc
                    market=market,
                    bankroll=prefs.bankroll,
                    kelly_fraction_setting=prefs.kelly_fraction,
                    max_bet_pct=prefs.max_bet_pct,
                    max_exposure=prefs.bankroll * prefs.max_total_exposure,
                    current_exposure=current_exposure,
                    min_bet_size=prefs.min_bet_size,
                )
                if sizing and sizing.bet_amount > 0:
                    bet_amount = sizing.bet_amount
                    sizing_details = sizing.model_dump(mode="json")
                    current_exposure += sizing.bet_amount
            except Exception as e:
                logger.warning("Sizing failed for user %s on market %s: %s", user_id, dr.market_id, e)

        alert = GeneratedAlert(
            user_id=user_id,
            debate_result_id=dr.id,
            cycle_id=dr.cycle_id,
            market_id=dr.market_id,
            market_question=dr.market_question,
            polymarket_probability=poly_prob,
            ai_probability=ai_prob,
            divergence=divergence,
            recommended_side=recommended_side,
            bet_amount=bet_amount,
            sizing_details=sizing_details,
            whale_signals=whale_scan_data.get(dr.market_id, []) if whale_scan_data else [],
        )
        alerts.append(alert)

    return alerts
