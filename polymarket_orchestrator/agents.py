from __future__ import annotations

import asyncio
import json
import logging

import anthropic

from polymarket_orchestrator.config import settings
from polymarket_orchestrator.models import AgentOpinion, DebateResult, Market

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent persona definitions
# ---------------------------------------------------------------------------

BULL_SYSTEM = """\
You are the Bull Analyst — an optimistic prediction market analyst.
Your job is to argue FOR the primary outcome ("Yes") of a prediction market.

Approach:
- Look for catalysts, momentum, and supporting evidence that the event WILL happen.
- Identify underappreciated factors that increase the likelihood.
- Consider recent trends, insider signals, and positive precedents.
- Be persuasive but intellectually honest — acknowledge weak points briefly.

You MUST respond with ONLY a JSON object (no markdown, no extra text):
{
  "probability": <float 0.0 to 1.0>,
  "reasoning": "<your 2-3 paragraph argument>",
  "confidence": "<low|medium|high>"
}"""

BEAR_SYSTEM = """\
You are the Bear Analyst — a skeptical prediction market analyst.
Your job is to argue AGAINST the primary outcome ("Yes") of a prediction market.

Approach:
- Look for risks, counter-evidence, and reasons the event will NOT happen.
- Identify overreaction, hype, or wishful thinking in current pricing.
- Consider historical base rates of failure, obstacles, and downside scenarios.
- Be persuasive but intellectually honest — acknowledge strong counter-arguments briefly.

You MUST respond with ONLY a JSON object (no markdown, no extra text):
{
  "probability": <float 0.0 to 1.0>,
  "reasoning": "<your 2-3 paragraph argument>",
  "confidence": "<low|medium|high>"
}"""

ANALYST_SYSTEM = """\
You are the Data Analyst — a neutral, data-driven prediction market analyst.
Your job is to provide an objective probability estimate based on evidence.

Approach:
- Focus on base rates, historical analogies, and statistical reasoning.
- Weigh the strength of available evidence dispassionately.
- Consider both sides equally and identify the most likely outcome.
- Flag key uncertainties and what information would change your estimate.

You MUST respond with ONLY a JSON object (no markdown, no extra text):
{
  "probability": <float 0.0 to 1.0>,
  "reasoning": "<your 2-3 paragraph analysis>",
  "confidence": "<low|medium|high>"
}"""

SYNTHESIZER_SYSTEM = """\
You are the Synthesis Judge — a meta-analyst who aggregates multiple expert opinions \
into a final probability estimate for a prediction market outcome.

You will receive arguments from three analysts (Bull, Bear, Data Analyst) with their \
individual probability estimates and reasoning.

Your job:
- Evaluate the strength and quality of each argument.
- Identify which analysts made the strongest evidence-based points.
- Weight opinions by argument quality, not just averaging.
- Account for common biases (anchoring to current market price, overconfidence).
- Produce a final calibrated probability that reflects the true likelihood.

You MUST respond with ONLY a JSON object (no markdown, no extra text):
{
  "probability": <float 0.0 to 1.0>,
  "reasoning": "<your 2-3 paragraph synthesis explaining your weighting>"
}"""


def _build_market_context(market: Market) -> str:
    """Build the user prompt with market details for debate agents."""
    prices = "\n".join(
        f"  - {t.outcome}: {t.price:.1%}" for t in market.tokens
    )
    return f"""\
Prediction Market Question: {market.question}

Description: {market.description}

Outcomes and Current Polymarket Prices:
{prices}

End Date: {market.end_date or "Not specified"}
Volume: ${market.volume:,.0f}
Liquidity: ${market.liquidity:,.0f}

Analyze this market and provide your probability estimate for the "Yes" outcome \
(or the first listed outcome). Consider what information is publicly available \
as of today's date. Respond with ONLY a JSON object."""


def _build_synthesis_prompt(market: Market, opinions: list[AgentOpinion]) -> str:
    """Build the synthesis prompt with all agent opinions."""
    parts = [f"Market: {market.question}\n"]
    for op in opinions:
        parts.append(
            f"--- {op.agent_name} (probability: {op.probability:.1%}, "
            f"confidence: {op.confidence}) ---\n{op.reasoning}\n"
        )
    parts.append(
        "\nSynthesize these opinions into a final calibrated probability. "
        "Respond with ONLY a JSON object."
    )
    return "\n".join(parts)


def _parse_agent_response(text: str) -> dict:
    """Parse JSON from agent response, handling markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code fence
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


async def _call_agent(
    client: anthropic.AsyncAnthropic,
    system: str,
    user_prompt: str,
    agent_name: str,
) -> AgentOpinion:
    """Call a single debate agent and return its opinion."""
    try:
        response = await client.messages.create(
            model=settings.debate_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = _parse_agent_response(response.content[0].text)
        return AgentOpinion(
            agent_name=agent_name,
            probability=float(raw["probability"]),
            reasoning=raw["reasoning"],
            confidence=raw.get("confidence", "medium"),
        )
    except Exception as e:
        logger.error("Agent %s failed: %s", agent_name, e)
        return AgentOpinion(
            agent_name=agent_name,
            probability=0.5,
            reasoning=f"Agent failed to respond: {e}",
            confidence="low",
        )


async def run_debate(market: Market) -> DebateResult:
    """Run a multi-agent debate on a single market and return the result."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_prompt = _build_market_context(market)

    # Run Bull, Bear, Analyst in parallel
    opinions = await asyncio.gather(
        _call_agent(client, BULL_SYSTEM, user_prompt, "Bull"),
        _call_agent(client, BEAR_SYSTEM, user_prompt, "Bear"),
        _call_agent(client, ANALYST_SYSTEM, user_prompt, "Analyst"),
    )
    opinions = list(opinions)

    # Synthesizer aggregates
    synthesis_prompt = _build_synthesis_prompt(market, opinions)
    try:
        synth_response = await client.messages.create(
            model=settings.debate_model,
            max_tokens=1024,
            system=SYNTHESIZER_SYSTEM,
            messages=[{"role": "user", "content": synthesis_prompt}],
        )
        synth = _parse_agent_response(synth_response.content[0].text)
        consensus = float(synth["probability"])
        synthesis_reasoning = synth["reasoning"]
    except Exception as e:
        logger.error("Synthesizer failed: %s", e)
        # Fallback: weighted average (Analyst gets 2x weight)
        weights = {"Bull": 1, "Bear": 1, "Analyst": 2}
        total_w = sum(weights.get(o.agent_name, 1) for o in opinions)
        consensus = sum(
            o.probability * weights.get(o.agent_name, 1) for o in opinions
        ) / total_w
        synthesis_reasoning = f"Synthesizer failed ({e}). Using weighted average."

    return DebateResult(
        market=market,
        opinions=opinions,
        consensus_probability=consensus,
        synthesis_reasoning=synthesis_reasoning,
    )
