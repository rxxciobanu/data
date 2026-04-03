"""Kelly Criterion position sizing for binary prediction markets.

Computes optimal bet size given:
- AI consensus probability vs. market price (the "edge")
- Fractional Kelly scaling (default quarter-Kelly for safety)
- Confidence/agreement discount from agent opinions
- Per-market, portfolio-level, and liquidity risk caps

Kelly formula for binary markets (derived from f* = (bp - q) / b):

  YES bet:  f* = (p - c) / (1 - c)
  NO  bet:  f* = (c - p) / c

where p = AI probability of YES, c = market price of YES token.

References:
  Kelly, J. L. (1956). "A New Interpretation of Information Rate."
  Bell System Technical Journal 35(4): 917–926.

  Thorp, E. O. (2006). "The Kelly Criterion in Blackjack, Sports Betting
  and the Stock Market." Handbook of Asset and Liability Management.
"""
from __future__ import annotations

import logging
import math

from polymarket_orchestrator.aggregation import CONFIDENCE_WEIGHTS
from polymarket_orchestrator.models import AgentOpinion, BetSizing, Market

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

_EPS = 0.01  # Probability clamp epsilon (same as aggregation.py)
_MAX_RAW_KELLY = 0.60  # Hard cap — anything higher signals data issues
_RAW_KELLY_WARN = 0.50  # Log warning above this
_DISAGREEMENT_SENSITIVITY = 2.0  # Multiplier on stdev for agreement score
_CONSERVATIVE_AGREEMENT = 0.3  # Default agreement when < 2 valid opinions
_LIQUIDITY_FRACTION = 0.10  # Don't take > 10% of market depth
_MAX_CONFIDENCE_WEIGHT = max(CONFIDENCE_WEIGHTS.values())  # Dynamic, not hardcoded 3.0


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _clamp_prob(p: float) -> float:
    """Clamp probability to [_EPS, 1 - _EPS] to prevent division by zero."""
    return max(_EPS, min(1.0 - _EPS, p))


def _is_failed_agent(opinion: AgentOpinion) -> bool:
    """Detect opinions from agents that failed (crash/timeout fallback)."""
    return opinion.reasoning.lower().startswith("agent failed")


# -----------------------------------------------------------------------
# Core Kelly fraction
# -----------------------------------------------------------------------

def kelly_fraction(ai_prob: float, market_prob: float, side: str) -> float:
    """Compute raw Kelly fraction f* for a binary prediction market bet.

    Args:
        ai_prob: AI consensus probability of YES (0–1).
        market_prob: Current market price of YES token (0–1).
        side: "YES" or "NO".

    Returns:
        Raw Kelly fraction clamped to [0, _MAX_RAW_KELLY].

    Formulas (derived from standard Kelly f* = (bp - q) / b):
        YES:  f* = (p - c) / (1 - c)    where p=ai_prob, c=market_prob
        NO:   f* = (c - p) / c
    """
    p = _clamp_prob(ai_prob)
    c = _clamp_prob(market_prob)

    if side.upper() == "YES":
        raw = (p - c) / (1.0 - c)
    else:  # NO
        raw = (c - p) / c

    # Negative edge → no bet
    if raw <= 0.0:
        return 0.0

    if raw > _RAW_KELLY_WARN:
        logger.warning(
            "Raw Kelly fraction %.1f%% is unusually high (ai=%.2f, mkt=%.2f, side=%s). "
            "Check data quality.",
            raw * 100, ai_prob, market_prob, side,
        )

    return min(raw, _MAX_RAW_KELLY)


# -----------------------------------------------------------------------
# Confidence multiplier
# -----------------------------------------------------------------------

def confidence_multiplier(opinions: list[AgentOpinion]) -> float:
    """Discount factor based on agent confidence levels and inter-agent agreement.

    Combines two signals:
    1. Mean confidence score: how individually confident the agents are.
       Range [1/max_weight, 1.0], e.g. [0.33, 1.0] with default weights.
    2. Agreement score: how much agents agree with each other.
       Uses population stdev of probabilities. Range [0.2, 1.0].

    The product gives a multiplier in roughly [0.07, 1.0].

    Args:
        opinions: Agent opinions (failed agents are filtered out).

    Returns:
        Discount multiplier in (0, 1]. Lower = less confident = smaller bet.
    """
    # Filter out failed agents
    valid = [op for op in opinions if not _is_failed_agent(op)]

    if not valid:
        logger.warning("No valid agent opinions for confidence multiplier. Using floor.")
        return 0.1

    # Signal 1: Mean confidence weight, normalized to [0, 1]
    weights = [CONFIDENCE_WEIGHTS.get(op.confidence.lower(), 2.0) for op in valid]
    mean_weight = sum(weights) / len(weights)
    conf_score = mean_weight / _MAX_CONFIDENCE_WEIGHT

    # Signal 2: Agent agreement (population stdev of probabilities)
    if len(valid) < 2:
        # Single opinion — can't measure agreement, use conservative default
        agreement_score = _CONSERVATIVE_AGREEMENT
    else:
        probs = [op.probability for op in valid]
        mean_p = sum(probs) / len(probs)
        variance = sum((p - mean_p) ** 2 for p in probs) / len(probs)  # population variance
        stdev = math.sqrt(variance)
        agreement_score = max(0.2, 1.0 - _DISAGREEMENT_SENSITIVITY * stdev)

    multiplier = conf_score * agreement_score

    if multiplier < 0.1:
        logger.info(
            "Confidence multiplier very low (%.3f): conf=%.2f, agree=%.2f. "
            "Bet will be heavily discounted.",
            multiplier, conf_score, agreement_score,
        )

    return multiplier


# -----------------------------------------------------------------------
# Main entry: compute full bet sizing
# -----------------------------------------------------------------------

def compute_bet_size(
    ai_prob: float,
    market_prob: float,
    side: str,
    opinions: list[AgentOpinion],
    market: Market,
    bankroll: float,
    kelly_fraction_setting: float = 0.25,
    max_bet_pct: float = 0.05,
    max_exposure: float = 2500.0,
    current_exposure: float = 0.0,
    min_bet_size: float = 5.0,
) -> BetSizing | None:
    """Compute position size for a single market bet.

    Pipeline:
      1. Raw Kelly f*
      2. × fractional Kelly (e.g. 0.25 for quarter-Kelly)
      3. × confidence multiplier
      4. → dollar amount
      5. Apply risk caps (per-market, portfolio, liquidity, min-bet)

    Args:
        ai_prob: AI consensus probability of YES.
        market_prob: Market price of YES token.
        side: "YES" or "NO".
        opinions: Agent opinions for confidence scoring.
        market: Market object (for liquidity data).
        bankroll: Total bankroll in dollars.
        kelly_fraction_setting: Fractional Kelly (0.25 = quarter-Kelly).
        max_bet_pct: Max fraction of bankroll per market (default 5%).
        max_exposure: Max total exposure in dollars across all bets.
        current_exposure: How much is already allocated to prior bets.
        min_bet_size: Minimum actionable bet (default $5).

    Returns:
        BetSizing with full breakdown, or None for non-binary markets.
    """
    # Guard: only binary markets
    if len(market.tokens) != 2:
        logger.info(
            "Skipping sizing for non-binary market (%d outcomes): %s",
            len(market.tokens), market.question,
        )
        return None

    # Step 1: Raw Kelly
    raw = kelly_fraction(ai_prob, market_prob, side)
    edge = abs(ai_prob - market_prob)

    # Step 2: Fractional Kelly
    fractional = raw * kelly_fraction_setting

    # Step 3: Confidence multiplier
    conf_mult = confidence_multiplier(opinions)
    kelly_final = fractional * conf_mult

    # Step 4: Dollar amount
    raw_amount = kelly_final * bankroll

    # Step 5: Risk caps
    cap_per_market = bankroll * max_bet_pct
    cap_portfolio = max(0.0, max_exposure - current_exposure)
    cap_liquidity = market.liquidity * _LIQUIDITY_FRACTION if market.liquidity > 0 else float("inf")

    caps = {
        "per-market": cap_per_market,
        "portfolio": cap_portfolio,
        "liquidity": cap_liquidity,
    }

    # Find the binding cap
    final_amount = raw_amount
    cap_reason = ""
    capped = False

    binding_cap_name = min(caps, key=caps.get)
    binding_cap_value = caps[binding_cap_name]

    if final_amount > binding_cap_value:
        final_amount = binding_cap_value
        cap_reason = binding_cap_name
        capped = True

    # Non-negative floor
    final_amount = max(0.0, final_amount)

    # Min bet threshold: if too small to be actionable, zero it out
    if 0 < final_amount < min_bet_size:
        final_amount = 0.0
        cap_reason = "min-bet"
        capped = True

    return BetSizing(
        kelly_raw=raw,
        kelly_fractional=fractional,
        confidence_mult=conf_mult,
        kelly_final=kelly_final,
        bet_amount=round(final_amount, 2),
        bet_pct_bankroll=final_amount / bankroll if bankroll > 0 else 0.0,
        bankroll=bankroll,
        edge=edge,
        capped=capped,
        cap_reason=cap_reason,
    )
