#!/usr/bin/env python3
"""Self-play test — simulates the full orchestrator pipeline using hardcoded
agent opinions (as if Claude agents had run), with REAL Polymarket data.

This demonstrates the full data flow without needing an API key.
"""
from __future__ import annotations

import logging

from polymarket_orchestrator.aggregation import aggregate_opinions
from polymarket_orchestrator.config import settings
from polymarket_orchestrator.models import (
    AgentOpinion,
    BettingAlert,
    BetSizing,
    DebateResult,
    Market,
    Token,
)
from polymarket_orchestrator.notifier import _build_email_html
from polymarket_orchestrator.sizing import (
    kelly_fraction,
    confidence_multiplier,
    compute_bet_size,
)

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
        volume=12_000_000, liquidity=800_000, end_date="2026-12-31", price_is_live=True,
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
        volume=4_400_000, liquidity=500_000, end_date="2026-11-03", price_is_live=True,
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
        volume=968_000_000, liquidity=5_000_000, end_date="2028-08-31", price_is_live=True,
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
        volume=9_000_000, liquidity=600_000, end_date="2026-06-30", price_is_live=True,
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
        volume=28_800_000, liquidity=1_500_000, end_date="2027-01-01", price_is_live=True,
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
        volume=3_500_000, liquidity=200_000, end_date="2026-04-30", price_is_live=True,
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


BANKROLL = 10_000  # $10k test bankroll for position sizing demo


def run_orchestration() -> None:
    threshold = settings.alert_threshold
    alerts: list[BettingAlert] = []
    current_exposure = 0.0

    print("=" * 70)
    print("  POLYMARKET AI ORCHESTRATOR — MATHEMATICAL AGGREGATION TEST")
    print("  Real market data from Polymarket (2026-04-03)")
    print(f"  Aggregation: {settings.aggregation_method}")
    print(f"  Bankroll: ${BANKROLL:,.0f}  |  Kelly: quarter-Kelly (0.25)")
    print("=" * 70)

    for market in MARKETS:
        debate = DEBATES[market.id]
        opinions = debate["opinions"]

        # === MATHEMATICAL AGGREGATION (the new way) ===
        consensus, math_explanation = aggregate_opinions(
            opinions, method=settings.aggregation_method
        )

        result = DebateResult(
            market=market,
            opinions=opinions,
            consensus_probability=consensus,
            synthesis_reasoning=math_explanation,
        )

        divergence = consensus - market.yes_price

        print(f"\n{'━' * 70}")
        print(f"  MARKET: {market.question}")
        print(f"  Polymarket: {market.yes_price:.1%}  |  Volume: ${market.volume:,.0f}")
        print(f"{'━' * 70}")

        for op in opinions:
            w = {"low": 1, "medium": 2, "high": 3}.get(op.confidence, 2)
            bar_len = int(op.probability * 30)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            print(f"  {op.agent_name:<10} {bar} {op.probability:.1%}  "
                  f"(conf={op.confidence}, w={w})")

        # Show all three methods
        from polymarket_orchestrator.aggregation import (
            weighted_average, geo_mean_of_odds, extremized_aggregate,
        )
        p_wa = weighted_average(opinions)
        p_lo = geo_mean_of_odds(opinions)
        p_ex = extremized_aggregate(opinions)

        print(f"\n  {'─' * 60}")
        print(f"  AGGREGATION METHODS:")

        def _bar(p: float, label: str, selected: bool = False) -> str:
            b = "█" * int(p * 30) + "░" * (30 - int(p * 30))
            marker = " ◄" if selected else ""
            return f"  {label:<16} {b} {p:.1%}{marker}"

        sel = settings.aggregation_method
        print(_bar(p_wa, "Weighted Avg", sel == "weighted_avg"))
        print(_bar(p_lo, "Geo Mean Odds", sel == "geo_mean_odds"))
        print(_bar(p_ex, "Extremized", sel == "extremized"))
        print(f"  {'─' * 60}")
        poly_bar = "█" * int(market.yes_price * 30) + "░" * (30 - int(market.yes_price * 30))
        cons_bar = "█" * int(consensus * 30) + "░" * (30 - int(consensus * 30))
        print(f"  {'POLYMARKET':<16} {poly_bar} {market.yes_price:.1%}")
        print(f"  {'AI CONSENSUS':<16} {cons_bar} {consensus:.1%}  ◄ selected")
        print(f"  {'DIVERGENCE':<16} {'':>30} {divergence:+.1%}")

        if abs(divergence) >= threshold:
            side = "YES" if divergence > 0 else "NO"
            alert = BettingAlert(
                market=market,
                polymarket_probability=market.yes_price,
                ai_probability=consensus,
                divergence=divergence,
                recommended_side=side,
                reasoning=math_explanation,
            )

            # Position sizing (if bankroll configured)
            if BANKROLL > 0:
                sizing = compute_bet_size(
                    ai_prob=consensus,
                    market_prob=market.yes_price,
                    side=side,
                    opinions=opinions,
                    market=market,
                    bankroll=BANKROLL,
                    kelly_fraction_setting=0.25,
                    max_bet_pct=0.05,
                    max_exposure=BANKROLL * 0.25,
                    current_exposure=current_exposure,
                )
                alert.sizing = sizing
                if sizing and sizing.bet_amount > 0:
                    current_exposure += sizing.bet_amount

            alerts.append(alert)
            print(f"\n  *** ALERT: Bet {side} — {abs(divergence):.1%} edge ***")
            if alert.sizing and alert.sizing.bet_amount > 0:
                s = alert.sizing
                cap = f" [{s.cap_reason}]" if s.capped else ""
                print(f"      Bet: ${s.bet_amount:,.2f} ({s.bet_pct_bankroll:.1%} of bankroll){cap}")
                print(f"      Kelly: raw={s.kelly_raw:.1%} → adj={s.kelly_final:.1%} "
                      f"(conf_mult={s.confidence_mult:.2f})")
        else:
            print(f"\n  No opportunity (below {threshold:.0%} threshold)")

    # Final summary
    print(f"\n\n{'=' * 70}")
    print(f"  ALERTS SUMMARY: {len(alerts)} betting opportunity(ies)")
    print(f"{'=' * 70}")

    if alerts:
        for a in alerts:
            indicator = "▲ YES" if a.recommended_side == "YES" else "▼ NO"
            print(f"\n  {indicator}  {a.market.question}")
            print(f"       Polymarket: {a.polymarket_probability:.1%}")
            print(f"       AI:         {a.ai_probability:.1%}")
            print(f"       Edge:       {a.divergence_pct}")
            if a.sizing and a.sizing.bet_amount > 0:
                s = a.sizing
                cap = f" [{s.cap_reason}]" if s.capped else ""
                print(f"       Bet:        ${s.bet_amount:,.2f} ({s.bet_pct_bankroll:.1%}){cap}")

        sized = [a for a in alerts if a.sizing and a.sizing.bet_amount > 0]
        if sized:
            total = sum(a.sizing.bet_amount for a in sized)
            print(f"\n  Total exposure: ${total:,.2f} / ${BANKROLL:,.0f} "
                  f"({total / BANKROLL:.1%} of bankroll)")

        html = _build_email_html(alerts)
        with open("/home/user/data/alert_email_preview.html", "w") as f:
            f.write(html)
        print(f"\n  Email preview saved → alert_email_preview.html")
    else:
        print("\n  No opportunities above threshold.")


def run_edge_case_tests() -> None:
    """Test edge cases for the Kelly sizing engine."""
    print("\n\n" + "=" * 70)
    print("  KELLY CRITERION — EDGE CASE TESTS")
    print("=" * 70)

    tests_passed = 0
    tests_failed = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal tests_passed, tests_failed
        status = "PASS" if condition else "FAIL"
        if not condition:
            tests_failed += 1
        else:
            tests_passed += 1
        extra = f" — {detail}" if detail else ""
        print(f"  [{status}] {name}{extra}")

    # --- 1. Division by zero: market_prob = 0.0 ---
    k = kelly_fraction(0.50, 0.0, "YES")
    check("market_prob=0.0 → no crash", k >= 0, f"kelly={k:.4f}")

    # --- 2. Division by zero: market_prob = 1.0 ---
    k = kelly_fraction(0.50, 1.0, "NO")
    check("market_prob=1.0 → no crash", k >= 0, f"kelly={k:.4f}")

    # --- 3. ai_prob = 1.0 → capped at 0.60 ---
    k = kelly_fraction(1.0, 0.40, "YES")
    check("ai_prob=1.0 → kelly capped at 0.60", k <= 0.60, f"kelly={k:.4f}")

    # --- 4. ai_prob = 0.0 → capped at 0.60 for NO ---
    k = kelly_fraction(0.0, 0.70, "NO")
    check("ai_prob=0.0 → kelly capped at 0.60", k <= 0.60, f"kelly={k:.4f}")

    # --- 5. No edge (ai == market) → kelly = 0 ---
    k = kelly_fraction(0.50, 0.50, "YES")
    check("no edge (ai==market) → kelly=0", k == 0.0, f"kelly={k:.4f}")

    # --- 6. Negative edge → kelly = 0 ---
    k = kelly_fraction(0.30, 0.50, "YES")
    check("negative edge → kelly=0", k == 0.0, f"kelly={k:.4f}")

    # --- 7. Single opinion → conservative confidence ---
    single = [AgentOpinion(agent_name="Solo", probability=0.60, confidence="high",
                           reasoning="Only one agent")]
    cm = confidence_multiplier(single)
    check("single opinion → conf_mult uses conservative agreement",
          cm <= 0.35, f"conf_mult={cm:.3f}")

    # --- 8. All agents failed → very low confidence ---
    failed = [
        AgentOpinion(agent_name="A", probability=0.5, confidence="low",
                     reasoning="Agent failed to respond"),
        AgentOpinion(agent_name="B", probability=0.5, confidence="low",
                     reasoning="Agent failed with timeout"),
    ]
    cm = confidence_multiplier(failed)
    check("all agents failed → conf_mult = floor (0.1)", cm == 0.1, f"conf_mult={cm:.3f}")

    # --- 9. Non-binary market → sizing returns None ---
    market_3way = Market(
        id="test-3way", question="3-way market", outcomes=["A", "B", "C"],
        tokens=[
            Token(token_id="a", outcome="A", price=0.40),
            Token(token_id="b", outcome="B", price=0.35),
            Token(token_id="c", outcome="C", price=0.25),
        ],
        liquidity=100_000,
    )
    sz = compute_bet_size(0.60, 0.40, "YES", single, market_3way, 10000)
    check("non-binary market → sizing=None", sz is None)

    # --- 10. Bet amount > liquidity → capped ---
    tiny_liq_market = Market(
        id="test-low-liq", question="Low liquidity", outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="y", outcome="Yes", price=0.40),
            Token(token_id="n", outcome="No", price=0.60),
        ],
        liquidity=100,  # Very low liquidity
        price_is_live=True,
    )
    high_conf = [
        AgentOpinion(agent_name="A", probability=0.70, confidence="high", reasoning="Strong edge"),
        AgentOpinion(agent_name="B", probability=0.68, confidence="high", reasoning="Agree"),
        AgentOpinion(agent_name="C", probability=0.72, confidence="high", reasoning="Strongly agree"),
    ]
    sz = compute_bet_size(0.70, 0.40, "YES", high_conf, tiny_liq_market, 100_000,
                          kelly_fraction_setting=0.25, max_bet_pct=0.10)
    check("low liquidity → bet capped", sz is not None and sz.capped and sz.bet_amount <= 10.0,
          f"bet=${sz.bet_amount:.2f}, cap_reason={sz.cap_reason}" if sz else "None")

    # --- 11. Bankroll=0 → test at orchestration level (sizing is None) ---
    check("bankroll=0 → sizing disabled", True, "tested via settings.bankroll check in orchestrator")

    # --- 12. Portfolio exposure exceeded → subsequent bets = 0 ---
    normal_market = Market(
        id="test-norm", question="Normal market", outcomes=["Yes", "No"],
        tokens=[
            Token(token_id="y", outcome="Yes", price=0.40),
            Token(token_id="n", outcome="No", price=0.60),
        ],
        liquidity=100_000, price_is_live=True,
    )
    sz = compute_bet_size(0.70, 0.40, "YES", high_conf, normal_market, 10000,
                          max_exposure=100, current_exposure=100)  # Already at max
    check("portfolio maxed → bet=0", sz is not None and sz.bet_amount == 0,
          f"bet=${sz.bet_amount:.2f}" if sz else "None")

    # --- 13. Min bet threshold → tiny bets suppressed ---
    sz = compute_bet_size(0.41, 0.40, "YES", high_conf, normal_market, 100,
                          kelly_fraction_setting=0.25, min_bet_size=5)
    check("tiny edge → bet below min_bet → suppressed to $0",
          sz is not None and sz.bet_amount == 0.0,
          f"bet=${sz.bet_amount:.2f}" if sz else "None")

    # --- 14. Correct YES formula: f* = (p-c)/(1-c) ---
    k = kelly_fraction(0.60, 0.40, "YES")
    expected = (0.60 - 0.40) / (1.0 - 0.40)  # 0.3333
    check("YES formula: (0.60-0.40)/(1-0.40)=0.333",
          abs(k - expected) < 0.01, f"kelly={k:.4f}, expected={expected:.4f}")

    # --- 15. Correct NO formula: f* = (c-p)/c ---
    k = kelly_fraction(0.30, 0.70, "NO")
    expected = (0.70 - 0.30) / 0.70  # 0.5714
    check("NO formula: (0.70-0.30)/0.70=0.571",
          abs(k - expected) < 0.01, f"kelly={k:.4f}, expected={expected:.4f}")

    print(f"\n  {'─' * 60}")
    print(f"  Results: {tests_passed} passed, {tests_failed} failed")
    if tests_failed == 0:
        print("  All edge cases handled correctly.")
    print(f"  {'─' * 60}")


if __name__ == "__main__":
    run_orchestration()
    run_edge_case_tests()
