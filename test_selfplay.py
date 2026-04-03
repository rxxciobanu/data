#!/usr/bin/env python3
"""Self-play test — simulates the full orchestrator pipeline using hardcoded
agent opinions (as if Claude agents had run), with REAL Polymarket data.

This demonstrates the full data flow without needing an API key.
"""
from __future__ import annotations

import logging

from polymarket_orchestrator.config import settings
from polymarket_orchestrator.models import (
    AgentOpinion,
    BettingAlert,
    DebateResult,
    Market,
    Token,
)
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
MARKETS = [
    Market(
        id="us-recession-2026",
        question="US recession by end of 2026?",
        description="NBER-declared recession starting on or before Dec 31, 2026.",
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="recession-yes", outcome="Yes", price=0.35),
            Token(token_id="recession-no", outcome="No", price=0.645),
        ],
        volume=12_000_000, liquidity=800_000, end_date="2026-12-31",
    ),
    Market(
        id="balance-of-power-2026",
        question="Balance of Power: 2026 Midterms — Democrats Sweep?",
        description="Democrats control both House and Senate after Nov 2026 midterms.",
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="dem-sweep-yes", outcome="Yes", price=0.51),
            Token(token_id="dem-sweep-no", outcome="No", price=0.49),
        ],
        volume=4_400_000, liquidity=500_000, end_date="2026-11-03",
    ),
    Market(
        id="dem-nominee-2028",
        question="Will Gavin Newsom be the Democratic Presidential Nominee in 2028?",
        description="Newsom wins 2028 Dem nomination. Leads at 25%, AOC at 8%.",
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="newsom-yes", outcome="Yes", price=0.25),
            Token(token_id="newsom-no", outcome="No", price=0.75),
        ],
        volume=968_000_000, liquidity=5_000_000, end_date="2028-08-31",
    ),
    Market(
        id="trump-china-visit",
        question="Will Trump visit China by June 30, 2026?",
        description="Trump official visit to China by June 30. Rescheduled to May 14-15.",
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="trump-china-yes", outcome="Yes", price=0.83),
            Token(token_id="trump-china-no", outcome="No", price=0.17),
        ],
        volume=9_000_000, liquidity=600_000, end_date="2026-06-30",
    ),
    Market(
        id="btc-90k-2026",
        question="Will Bitcoin hit $90,000 in 2026?",
        description="BTC/USD reaches $90k before Jan 1 2027. Currently ~$83-85k.",
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="btc-90k-yes", outcome="Yes", price=0.95),
            Token(token_id="btc-90k-no", outcome="No", price=0.05),
        ],
        volume=28_800_000, liquidity=1_500_000, end_date="2027-01-01",
    ),
    Market(
        id="us-tariff-china",
        question="US tariff rate on China stays at 5-15% on April 30?",
        description="Effective tariff between 5-15% on April 30. Currently 99% YES.",
        outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="tariff-yes", outcome="Yes", price=0.99),
            Token(token_id="tariff-no", outcome="No", price=0.01),
        ],
        volume=3_500_000, liquidity=200_000, end_date="2026-04-30",
    ),
]

# -----------------------------------------------------------------------
# Simulated agent debate results (as if Claude agents had debated)
# -----------------------------------------------------------------------
DEBATES: dict[str, dict] = {
    "us-recession-2026": {
        "opinions": [
            AgentOpinion(
                agent_name="Bull",
                probability=0.50,
                confidence="medium",
                reasoning=(
                    "Tariff escalation with China has disrupted supply chains. Iran tensions "
                    "spiked oil prices. Consumer confidence is declining. The yield curve "
                    "only recently uninverted — historically recessions follow 12-18 months "
                    "after inversion. The Sahm rule at 0.3% is close to triggering."
                ),
            ),
            AgentOpinion(
                agent_name="Bear",
                probability=0.25,
                confidence="medium",
                reasoning=(
                    "Labor market remains strong at 4.6% unemployment. The Sahm rule hasn't "
                    "triggered. Fiscal spending continues. The Fed has room to cut rates. "
                    "Iran tensions are already de-escalating. Markets have priced in tariff "
                    "impact and adapted supply chains."
                ),
            ),
            AgentOpinion(
                agent_name="Analyst",
                probability=0.40,
                confidence="medium",
                reasoning=(
                    "Base rate: ~15% of years see a recession. But conditional on current "
                    "indicators (post-inversion, trade war, geopolitical stress), the base "
                    "rate rises to ~35-45%. Key swing factor: whether tariff escalation "
                    "continues or a deal is reached at the May Trump-Xi summit."
                ),
            ),
        ],
        "consensus": 0.40,
        "synthesis": (
            "Weighting the Analyst's calibrated base-rate approach most heavily, with "
            "the Bull's valid concerns about tariff disruption balanced against the Bear's "
            "strong labor market argument. The 40% estimate reflects genuine uncertainty — "
            "above Polymarket's 35% as the market may be underweighting tariff contagion risks."
        ),
    },
    "balance-of-power-2026": {
        "opinions": [
            AgentOpinion(
                agent_name="Bull",
                probability=0.58,
                confidence="medium",
                reasoning=(
                    "Midterm elections historically favor the opposition party. Democrats are "
                    "heavily favored in the House (86%). Senate map in 2026 is more favorable "
                    "for Democrats than 2024. Presidential approval ratings are low, boosting "
                    "Democratic turnout motivation."
                ),
            ),
            AgentOpinion(
                agent_name="Bear",
                probability=0.38,
                confidence="medium",
                reasoning=(
                    "Senate races are structurally harder for Democrats. Even with a House win, "
                    "sweeping both chambers requires winning close Senate races. Historical "
                    "base rate for opposition sweeps in midterms is only ~30-40%. Gerrymandering "
                    "and incumbency advantages limit the wave."
                ),
            ),
            AgentOpinion(
                agent_name="Analyst",
                probability=0.48,
                confidence="medium",
                reasoning=(
                    "Generic ballot strongly favors Democrats (+8). House flip is likely (~85%). "
                    "Senate is the bottleneck — need to hold all seats + flip 1-2. Historical "
                    "analysis: opposition sweeps happen ~35% of midterms. Current conditions "
                    "(low approval, economy stress) push it slightly higher."
                ),
            ),
        ],
        "consensus": 0.48,
        "synthesis": (
            "The House is nearly locked for Democrats. The Senate is the swing factor. "
            "Combining the strong generic ballot with historical base rates for sweeps, "
            "48% is slightly below Polymarket's 51%, as markets may be overweighting "
            "the House strength without fully accounting for Senate difficulty."
        ),
    },
    "dem-nominee-2028": {
        "opinions": [
            AgentOpinion(
                agent_name="Bull",
                probability=0.32,
                confidence="medium",
                reasoning=(
                    "Newsom has strong name recognition, California fundraising base, and is "
                    "term-limited (can run full-time). Polling shows double-digit lead over "
                    "Harris among CA Democrats. He's positioned as the anti-Trump voice. "
                    "The field is fragmented with no clear alternative."
                ),
            ),
            AgentOpinion(
                agent_name="Bear",
                probability=0.18,
                confidence="medium",
                reasoning=(
                    "2028 is far away — frontrunner status this early is historically unreliable. "
                    "California governors have a poor track record in presidential primaries. "
                    "Newsom's record on homelessness and housing is a vulnerability. Other "
                    "candidates (Shapiro, Whitmer, Buttigieg) haven't ramped up yet."
                ),
            ),
            AgentOpinion(
                agent_name="Analyst",
                probability=0.22,
                confidence="low",
                reasoning=(
                    "Historical base rate: early frontrunners at 25% this far out win the "
                    "nomination ~30-40% of the time. But the field is wide and 2+ years "
                    "is an eternity in politics. Adjusting for field fragmentation and "
                    "Newsom's structural advantages, 20-25% feels fair."
                ),
            ),
        ],
        "consensus": 0.23,
        "synthesis": (
            "Newsom has genuine advantages but 2028 is too far out for high confidence. "
            "The 25% Polymarket price is roughly correct. Our 23% estimate suggests slight "
            "overpricing but within noise — not actionable."
        ),
    },
    "trump-china-visit": {
        "opinions": [
            AgentOpinion(
                agent_name="Bull",
                probability=0.88,
                confidence="high",
                reasoning=(
                    "The visit is already rescheduled with specific dates (May 14-15). Both "
                    "sides have confirmed. The Middle East situation is de-escalating. Trump "
                    "wants a trade deal win before midterms. Xi has incentive to reduce tariffs. "
                    "The 3-month window is generous."
                ),
            ),
            AgentOpinion(
                agent_name="Bear",
                probability=0.70,
                confidence="medium",
                reasoning=(
                    "It was already postponed once. Geopolitical surprises (Taiwan, Iran "
                    "escalation, domestic crisis) could force another delay. Health events "
                    "are always possible. The June 30 deadline leaves buffer but 'by June 30' "
                    "means the May dates must hold or a quick reschedule is needed."
                ),
            ),
            AgentOpinion(
                agent_name="Analyst",
                probability=0.82,
                confidence="high",
                reasoning=(
                    "Base rate for scheduled presidential foreign visits actually happening: "
                    "~85-90%. One postponement has already occurred (negative signal) but "
                    "rescheduling confirms intent. With specific dates set and both sides "
                    "confirmed, 80-85% is well-calibrated."
                ),
            ),
        ],
        "consensus": 0.82,
        "synthesis": (
            "Strong consensus across all agents. The visit is scheduled with specific dates, "
            "both sides are confirmed, and there's adequate buffer time. The market at 83% "
            "is well-priced. Our 82% is essentially in agreement — no trading opportunity."
        ),
    },
    "btc-90k-2026": {
        "opinions": [
            AgentOpinion(
                agent_name="Bull",
                probability=0.88,
                confidence="high",
                reasoning=(
                    "BTC is already at $83-85k, only ~7% away from $90k. 9 months remaining. "
                    "ETF inflows continue. The halving cycle historically peaks 12-18 months "
                    "post-halving (April 2024 halving → peak in late 2025/2026). Institutional "
                    "adoption accelerating."
                ),
            ),
            AgentOpinion(
                agent_name="Bear",
                probability=0.78,
                confidence="medium",
                reasoning=(
                    "While likely, recession risk could trigger a crypto selloff. Regulatory "
                    "uncertainty remains. The 95% market price leaves almost no room for "
                    "downside scenarios. A sustained bear market below $85k for 9 months "
                    "is unlikely but not impossible (5-15% chance)."
                ),
            ),
            AgentOpinion(
                agent_name="Analyst",
                probability=0.85,
                confidence="high",
                reasoning=(
                    "BTC is $5-7k from target with 9 months. Historical volatility means "
                    "BTC regularly moves 7%+ in a single week. Even in bearish scenarios, "
                    "a brief spike to $90k is likely. But the 95% market price overestimates "
                    "certainty — tail risks (exchange failures, regulatory crackdowns, "
                    "macro crash) deserve ~10-15% weight."
                ),
            ),
        ],
        "consensus": 0.85,
        "synthesis": (
            "All agents agree BTC is very likely to touch $90k given proximity and timeframe. "
            "However, the market at 95% is too confident — it doesn't adequately price tail "
            "risks. Our 85% consensus represents a meaningful 10% divergence, suggesting "
            "the NO side may be undervalued."
        ),
    },
    "us-tariff-china": {
        "opinions": [
            AgentOpinion(
                agent_name="Bull",
                probability=0.96,
                confidence="high",
                reasoning=(
                    "Current tariff rate is already in the 5-15% range. April 30 is only "
                    "27 days away. No scheduled tariff changes. Trump-Xi summit isn't until "
                    "May. It would take a sudden executive order to change rates this fast."
                ),
            ),
            AgentOpinion(
                agent_name="Bear",
                probability=0.92,
                confidence="medium",
                reasoning=(
                    "Trump has a history of surprise tariff announcements via Twitter/Truth "
                    "Social. A geopolitical incident (Taiwan, trade retaliation) could trigger "
                    "emergency tariff hikes. But the short timeframe and scheduled summit "
                    "create incentives to keep rates stable."
                ),
            ),
            AgentOpinion(
                agent_name="Analyst",
                probability=0.95,
                confidence="high",
                reasoning=(
                    "With 27 days to resolution and rates already in-band, the question is "
                    "whether an unexpected shock changes policy. Base rate for surprise tariff "
                    "changes in a given month: ~5-8%. The pre-summit period adds stability "
                    "incentive. 95% is well-calibrated."
                ),
            ),
        ],
        "consensus": 0.95,
        "synthesis": (
            "Very short timeframe with rates already in the target band. All agents cluster "
            "around 92-96%. Market at 99% may be slightly overconfident given Trump's "
            "unpredictability, but the 4% divergence is below our alert threshold."
        ),
    },
}


def run_orchestration() -> None:
    threshold = settings.alert_threshold
    alerts: list[BettingAlert] = []

    print("=" * 65)
    print("  POLYMARKET AI ORCHESTRATOR — FULL PIPELINE TEST")
    print("  Real market data from Polymarket (2026-04-03)")
    print("  Simulated 4-agent Claude debate per market")
    print("=" * 65)

    for market in MARKETS:
        debate = DEBATES[market.id]
        result = DebateResult(
            market=market,
            opinions=debate["opinions"],
            consensus_probability=debate["consensus"],
            synthesis_reasoning=debate["synthesis"],
        )

        divergence = result.consensus_probability - market.yes_price

        print(f"\n{'━' * 65}")
        print(f"  MARKET: {market.question}")
        print(f"  Polymarket: {market.yes_price:.0%}  |  Volume: ${market.volume:,.0f}")
        print(f"{'━' * 65}")

        for op in result.opinions:
            bar_len = int(op.probability * 30)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            print(f"  {op.agent_name:<10} {bar} {op.probability:.0%}  ({op.confidence})")
            # Wrap reasoning to 65 chars
            words = op.reasoning.split()
            line = "             "
            for w in words:
                if len(line) + len(w) + 1 > 63:
                    print(line)
                    line = "             " + w
                else:
                    line += " " + w if line.strip() else "             " + w
            if line.strip():
                print(line)
            print()

        print(f"  {'─' * 55}")
        bar_len = int(result.consensus_probability * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        print(f"  CONSENSUS  {bar} {result.consensus_probability:.0%}")
        print(f"  POLYMARKET {'█' * int(market.yes_price * 30)}{'░' * (30 - int(market.yes_price * 30))} {market.yes_price:.0%}")
        print(f"  DIVERGENCE {'':>30} {divergence:+.0%}")

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
            print(f"\n  *** ALERT: Bet {side} — {abs(divergence):.0%} edge detected ***")
        else:
            print(f"\n  No opportunity (divergence below {threshold:.0%} threshold)")

    # Final summary
    print(f"\n\n{'=' * 65}")
    print(f"  ALERTS SUMMARY: {len(alerts)} betting opportunity(ies) found")
    print(f"{'=' * 65}")

    if alerts:
        for a in alerts:
            indicator = "▲ YES" if a.recommended_side == "YES" else "▼ NO"
            print(f"\n  {indicator}  {a.market.question}")
            print(f"       Polymarket says: {a.polymarket_probability:.0%}")
            print(f"       AI consensus:    {a.ai_probability:.0%}")
            print(f"       Edge:            {a.divergence_pct}")
            print(f"       Reasoning: {a.reasoning[:120]}...")

        # Generate email
        html = _build_email_html(alerts)
        with open("/home/user/data/alert_email_preview.html", "w") as f:
            f.write(html)
        print(f"\n  Email preview saved → alert_email_preview.html ({len(html):,} chars)")
        print("  (Open in browser to see the formatted alert email)")
    else:
        print("\n  No opportunities above threshold. Markets are efficiently priced.")


if __name__ == "__main__":
    run_orchestration()
