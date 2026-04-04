"""Mathematical probability aggregation methods for multi-agent opinions.

Three methods are implemented, each grounded in forecasting research:

1. **Confidence-weighted average**: Arithmetic mean weighted by confidence.
   Simple baseline, but known to be under-confident (herds toward 50%).

2. **Geometric mean of odds** (log-odds pooling): The Bayesian-optimal
   aggregator. Averages in log-odds space (equivalent to the geometric
   mean of odds ratios). Satisfies "external Bayesianity" — the only
   pooling rule that does (Genest, 1984).

3. **Extremized geometric mean of odds**: The recommended method.
   Applies the geometric mean of odds, then raises the result to a
   power d > 1 to correct for shared information / herding.

   Source: Satopää, Baron, Foster, Mellers, Tetlock & Ungar (2014),
   "Combining multiple probability predictions using a simple logit model",
   International Journal of Forecasting 30(2): 344–356.

   The paper's formula for N experts with odds o_i = p_i / (1 - p_i):

     ô = (∏ o_i^(w_i))^(d / Σw_i)

   In log-odds space this becomes:

     L = d × Σ(w_i × ln(o_i)) / Σ(w_i)
     p = sigmoid(L) = 1 / (1 + e^(-L))

   Optimal d was found between 1.161 and 3.921 on IARPA ACE data,
   with d = 2.5 as the suggested heuristic for independent human
   forecasters.

Each method returns a probability clamped to [0.01, 0.99].
"""
from __future__ import annotations

import logging
import math

from polymarket_orchestrator.models import AgentOpinion

logger = logging.getLogger(__name__)

# Confidence label → numeric weight
CONFIDENCE_WEIGHTS: dict[str, float] = {
    "low": 1.0,
    "medium": 2.0,
    "high": 3.0,
}

# Small epsilon to keep log-odds finite
_EPS = 0.01


def _clamp(p: float) -> float:
    """Clamp probability to [0.01, 0.99]."""
    return max(_EPS, min(1.0 - _EPS, p))


def _confidence_weight(opinion: AgentOpinion) -> float:
    """Map an agent's confidence label to a numeric weight."""
    return CONFIDENCE_WEIGHTS.get(opinion.confidence.lower(), 2.0)


def _to_logodds(p: float) -> float:
    """Convert probability to log-odds: ln(p / (1 - p))."""
    p = _clamp(p)
    return math.log(p / (1.0 - p))


def _from_logodds(lo: float) -> float:
    """Convert log-odds back to probability: 1 / (1 + exp(-lo))."""
    # Clamp log-odds to avoid overflow in exp(). Widened to +-40 so
    # extremized high-consensus forecasts (e.g. d=2.5, agents at 0.99)
    # don't lose precision. sigmoid(40) ≈ 1 - 4e-18, safe for float64.
    lo = max(-40.0, min(40.0, lo))
    return _clamp(1.0 / (1.0 + math.exp(-lo)))


# -----------------------------------------------------------------------
# Method 1: Confidence-weighted linear average
# -----------------------------------------------------------------------

def weighted_average(opinions: list[AgentOpinion]) -> float:
    """Weighted arithmetic mean of agent probabilities.

    Formula:  p = Σ(w_i × p_i) / Σ(w_i)

    Simple but known to be poorly calibrated — it systematically
    underweights extreme probabilities and herds toward 50%.
    """
    if not opinions:
        return 0.5

    total_weight = 0.0
    weighted_sum = 0.0
    for op in opinions:
        w = _confidence_weight(op)
        weighted_sum += w * op.probability
        total_weight += w

    return _clamp(weighted_sum / total_weight)


# -----------------------------------------------------------------------
# Method 2: Geometric mean of odds (log-odds pooling)
# -----------------------------------------------------------------------

def geo_mean_of_odds(opinions: list[AgentOpinion]) -> float:
    """Confidence-weighted geometric mean of odds.

    This is equivalent to a weighted average in log-odds space.
    It is the only aggregation method that satisfies "external
    Bayesianity" (Genest 1984) and minimizes average KL divergence
    to the individual expert distributions.

    Formula:
      L = Σ(w_i × ln(p_i / (1 - p_i))) / Σ(w_i)
      p = 1 / (1 + e^(-L))

    Equivalently in odds space:
      ô = (∏ o_i^w_i)^(1 / Σw_i)    [weighted geometric mean]
      p = ô / (1 + ô)
    """
    if not opinions:
        return 0.5

    total_weight = 0.0
    weighted_logodds = 0.0
    for op in opinions:
        w = _confidence_weight(op)
        weighted_logodds += w * _to_logodds(op.probability)
        total_weight += w

    return _from_logodds(weighted_logodds / total_weight)


# -----------------------------------------------------------------------
# Method 3: Extremized geometric mean of odds (Satopää et al. 2014)
# -----------------------------------------------------------------------

def extremized_aggregate(
    opinions: list[AgentOpinion],
    extremization_factor: float = 1.5,
) -> float:
    """Geometric mean of odds raised to power d > 1.

    This is the method recommended by Satopää et al. (2014) for
    combining probability forecasts. It corrects for the well-documented
    tendency of forecast aggregates to be under-confident (too close
    to 50%), which arises from shared information among forecasters.

    Formula (the correct one from the paper):
      L = Σ(w_i × ln(p_i / (1 - p_i))) / Σ(w_i)   [geo mean of odds]
      L' = d × L                                     [extremize]
      p = 1 / (1 + e^(-L'))                          [back to prob]

    Equivalently in odds space:
      ô = (∏ o_i^w_i)^(d / Σw_i)
      p = ô / (1 + ô)

    IMPORTANT: The extremization factor d multiplies the LOG-ODDS
    from the geometric mean of odds — NOT from the arithmetic mean
    of probabilities. This distinction matters because the arithmetic
    mean and geometric mean of odds give different base values,
    especially for extreme probabilities.

    Optimal d from Satopää et al. (2014) on IARPA ACE geopolitical
    forecasting data: between 1.161 and 3.921, with d ≈ 2.5 as
    the suggested heuristic for pools of independent human forecasters.

    For LLM agents (which share training data and thus have correlated
    biases), we default to d = 1.5 to avoid over-extremizing.

    Args:
        opinions: Agent opinions with probabilities and confidence.
        extremization_factor: Power d. Default 1.5 for LLM agents.
            Use 2.5 for independent human forecasters.
    """
    if not opinions:
        return 0.5

    # Step 1: Weighted average in log-odds space (geometric mean of odds)
    total_weight = 0.0
    weighted_logodds = 0.0
    for op in opinions:
        w = _confidence_weight(op)
        weighted_logodds += w * _to_logodds(op.probability)
        total_weight += w
    geo_logodds = weighted_logodds / total_weight

    # Step 2: Extremize by multiplying log-odds by factor d
    extremized_logodds = geo_logodds * extremization_factor

    # Step 3: Convert back to probability
    return _from_logodds(extremized_logodds)


# -----------------------------------------------------------------------
# Unified aggregation function
# -----------------------------------------------------------------------

def aggregate_opinions(
    opinions: list[AgentOpinion],
    method: str = "extremized",
) -> tuple[float, str]:
    """Aggregate agent opinions into a consensus probability.

    Args:
        opinions: Agent opinions to aggregate.
        method: One of "weighted_avg", "geo_mean_odds", "extremized".

    Returns:
        (consensus_probability, explanation_string)
    """
    if not opinions:
        return 0.5, "No opinions to aggregate."

    # Warn if all agents returned identical probabilities (potential shared bias)
    probs = [op.probability for op in opinions]
    if len(set(probs)) == 1 and len(probs) > 1:
        logger.warning(
            "All %d agents returned identical probability %.2f. "
            "This may indicate shared bias or a prompt engineering failure.",
            len(probs), probs[0],
        )

    # Compute all three for the explanation
    p_weighted = weighted_average(opinions)
    p_geo = geo_mean_of_odds(opinions)
    p_extremized = extremized_aggregate(opinions)

    # Format the breakdown
    agent_parts = []
    for op in opinions:
        w = _confidence_weight(op)
        lo = _to_logodds(op.probability)
        agent_parts.append(
            f"{op.agent_name}: {op.probability:.1%} "
            f"(conf={op.confidence}, w={w:.0f}, log-odds={lo:+.3f})"
        )
    agent_summary = "\n".join(agent_parts)

    explanation = (
        f"Agent estimates:\n{agent_summary}\n\n"
        f"Aggregation results:\n"
        f"  Weighted average (arithmetic):   {p_weighted:.1%}\n"
        f"  Geometric mean of odds:          {p_geo:.1%}\n"
        f"  Extremized geo-mean (d=1.5):     {p_extremized:.1%}\n\n"
    )

    if method == "weighted_avg":
        result = p_weighted
        explanation += f"Selected: confidence-weighted average → {result:.1%}"
    elif method in ("geo_mean_odds", "log_odds"):
        result = p_geo
        explanation += f"Selected: geometric mean of odds → {result:.1%}"
    else:  # extremized (default)
        result = p_extremized
        explanation += (
            f"Selected: extremized geometric mean of odds → {result:.1%}\n"
            f"Formula: p = sigmoid(d × mean_log_odds), d=1.5\n"
            f"Source: Satopää et al. (2014), Int J Forecasting 30(2):344-356"
        )

    return result, explanation
