"""Mathematical probability aggregation methods for multi-agent opinions.

Three methods are implemented, each grounded in forecasting research:

1. **Confidence-weighted average**: Weights each agent's probability by a
   numeric confidence score. Simple and interpretable.

2. **Log-odds (logarithmic) pooling**: Averages in log-odds space, which
   respects the multiplicative nature of evidence. A 90% and a 10% average
   to 50% in linear space but remain more extreme in log-odds space when
   one agent has higher confidence.

3. **Extremized aggregate**: Takes a weighted average then pushes it away
   from 50% by a tunable factor. Corrects for the well-documented
   "herding toward 50%" bias in group forecasts (Satopää et al., 2014).

Each method returns a probability in [0.01, 0.99] to avoid degenerate
values at the boundaries.
"""
from __future__ import annotations

import math

from polymarket_orchestrator.models import AgentOpinion

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
    """Convert probability to log-odds: log(p / (1 - p))."""
    p = _clamp(p)
    return math.log(p / (1.0 - p))


def _from_logodds(lo: float) -> float:
    """Convert log-odds back to probability: 1 / (1 + exp(-lo))."""
    return _clamp(1.0 / (1.0 + math.exp(-lo)))


# -----------------------------------------------------------------------
# Method 1: Confidence-weighted linear average
# -----------------------------------------------------------------------

def weighted_average(opinions: list[AgentOpinion]) -> float:
    """Weighted arithmetic mean of agent probabilities.

    Each agent's estimate is weighted by their confidence level:
      low=1, medium=2, high=3.

    Formula:
      p = Σ(w_i * p_i) / Σ(w_i)
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
# Method 2: Log-odds pooling (logarithmic opinion pool)
# -----------------------------------------------------------------------

def log_odds_pooling(opinions: list[AgentOpinion]) -> float:
    """Confidence-weighted average in log-odds space.

    Log-odds pooling is the Bayesian-optimal way to combine independent
    probability estimates. It treats each agent's opinion as independent
    evidence and combines them multiplicatively.

    Formula:
      log_odds_combined = Σ(w_i * log(p_i / (1 - p_i))) / Σ(w_i)
      p = sigmoid(log_odds_combined)

    Properties:
    - A single high-confidence extreme opinion pulls harder than in
      linear averaging.
    - Symmetric: 80% and 20% with equal weights → exactly 50%.
    - Respects the information content of extreme probabilities.
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
# Method 3: Extremized aggregate
# -----------------------------------------------------------------------

def extremized_aggregate(
    opinions: list[AgentOpinion],
    extremization_factor: float = 1.5,
) -> float:
    """Weighted average with extremization to correct for herding.

    Forecaster groups systematically underreact — their average tends
    toward 50% more than the truth warrants. Extremization corrects this
    by raising the aggregate in log-odds space by a factor > 1.

    Based on: Satopää et al. (2014) "Combining multiple probability
    predictions using a simple logit model."

    Steps:
      1. Compute confidence-weighted linear average → p_bar
      2. Convert to log-odds → L = log(p_bar / (1 - p_bar))
      3. Extremize → L' = L * extremization_factor
      4. Convert back → p_final = sigmoid(L')

    Recommended factor values:
      1.0 = no correction (same as weighted average)
      1.5 = mild correction (default — good for diverse agent panels)
      2.5 = standard correction (IARPA ACE tournament calibration)
      3.5 = aggressive correction (very consensus-seeking agents)

    Args:
        opinions: List of agent opinions with probabilities and confidence.
        extremization_factor: How aggressively to push away from 50%.
            Default 1.5 (mild correction for diverse agent panels).
    """
    if not opinions:
        return 0.5

    # Step 1: confidence-weighted linear average
    p_bar = weighted_average(opinions)

    # Step 2-3: extremize in log-odds space
    logodds = _to_logodds(p_bar)
    extremized_logodds = logodds * extremization_factor

    # Step 4: back to probability
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
        method: One of "weighted_avg", "log_odds", "extremized".

    Returns:
        (consensus_probability, explanation_string)
    """
    if not opinions:
        return 0.5, "No opinions to aggregate."

    # Compute all three for the explanation
    p_weighted = weighted_average(opinions)
    p_logodds = log_odds_pooling(opinions)
    p_extremized = extremized_aggregate(opinions)

    # Format the breakdown
    agent_parts = []
    for op in opinions:
        w = _confidence_weight(op)
        agent_parts.append(
            f"{op.agent_name}: {op.probability:.1%} "
            f"(confidence={op.confidence}, weight={w:.0f})"
        )
    agent_summary = "\n".join(agent_parts)

    explanation = (
        f"Agent estimates:\n{agent_summary}\n\n"
        f"Aggregation results:\n"
        f"  Confidence-weighted average: {p_weighted:.1%}\n"
        f"  Log-odds pooling:            {p_logodds:.1%}\n"
        f"  Extremized (factor=1.5):     {p_extremized:.1%}\n\n"
    )

    if method == "weighted_avg":
        result = p_weighted
        explanation += f"Selected method: confidence-weighted average → {result:.1%}"
    elif method == "log_odds":
        result = p_logodds
        explanation += f"Selected method: log-odds pooling → {result:.1%}"
    else:  # extremized (default)
        result = p_extremized
        explanation += (
            f"Selected method: extremized aggregate → {result:.1%}\n"
            f"Extremization pushes the weighted average ({p_weighted:.1%}) "
            f"away from 50% to correct for agent herding bias."
        )

    return result, explanation
