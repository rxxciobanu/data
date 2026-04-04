"""Tests for alert service — per-user alert generation from debate results."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from saas.services.alert_service import generate_alerts_for_user


def _make_prefs(**overrides):
    """Create a mock UserPreferences with defaults."""
    defaults = dict(
        alert_threshold=0.10,
        alert_enabled=True,
        bankroll=0,
        kelly_fraction=0.25,
        max_bet_pct=0.05,
        max_total_exposure=0.25,
        min_bet_size=5.0,
        whale_enabled=False,
        whale_min_trade_size=1000,
    )
    defaults.update(overrides)
    prefs = MagicMock()
    for k, v in defaults.items():
        setattr(prefs, k, v)
    return prefs


def _make_debate_result(
    market_id: str = "m1",
    question: str = "Will BTC hit $100k?",
    poly_price: float = 0.50,
    ai_prob: float = 0.65,
    cycle_id: str = "2026-04-04T12:00:00Z",
):
    dr = MagicMock()
    dr.id = uuid.uuid4()
    dr.cycle_id = cycle_id
    dr.market_id = market_id
    dr.market_question = question
    dr.polymarket_price = poly_price
    dr.consensus_probability = ai_prob
    dr.market_data = {
        "id": market_id,
        "question": question,
        "description": "",
        "outcomes": ["Yes", "No"],
        "tokens": [
            {"token_id": "yes-1", "outcome": "Yes", "price": poly_price},
            {"token_id": "no-1", "outcome": "No", "price": 1 - poly_price},
        ],
    }
    return dr


def test_alert_generated_above_threshold():
    user_id = uuid.uuid4()
    prefs = _make_prefs(alert_threshold=0.10)
    debates = [_make_debate_result(ai_prob=0.65, poly_price=0.50)]  # 15% divergence

    alerts = generate_alerts_for_user(user_id, prefs, debates)
    assert len(alerts) == 1
    assert abs(alerts[0].divergence - 0.15) < 1e-10
    assert alerts[0].recommended_side == "YES"
    assert alerts[0].market_question == "Will BTC hit $100k?"


def test_no_alert_below_threshold():
    user_id = uuid.uuid4()
    prefs = _make_prefs(alert_threshold=0.10)
    debates = [_make_debate_result(ai_prob=0.55, poly_price=0.50)]  # 5% divergence

    alerts = generate_alerts_for_user(user_id, prefs, debates)
    assert len(alerts) == 0


def test_no_side_alert():
    user_id = uuid.uuid4()
    prefs = _make_prefs(alert_threshold=0.10)
    debates = [_make_debate_result(ai_prob=0.35, poly_price=0.50)]  # -15% divergence

    alerts = generate_alerts_for_user(user_id, prefs, debates)
    assert len(alerts) == 1
    assert alerts[0].recommended_side == "NO"


def test_multiple_markets():
    user_id = uuid.uuid4()
    prefs = _make_prefs(alert_threshold=0.05)
    debates = [
        _make_debate_result(market_id="m1", ai_prob=0.70, poly_price=0.50),  # 20%
        _make_debate_result(market_id="m2", ai_prob=0.52, poly_price=0.50),  # 2%  - below
        _make_debate_result(market_id="m3", ai_prob=0.30, poly_price=0.50),  # -20%
    ]

    alerts = generate_alerts_for_user(user_id, prefs, debates)
    assert len(alerts) == 2
    assert {a.market_id for a in alerts} == {"m1", "m3"}


def test_different_thresholds_different_users():
    debates = [_make_debate_result(ai_prob=0.58, poly_price=0.50)]  # 8% divergence

    # User A: 5% threshold → gets alert
    alerts_a = generate_alerts_for_user(uuid.uuid4(), _make_prefs(alert_threshold=0.05), debates)
    assert len(alerts_a) == 1

    # User B: 10% threshold → no alert
    alerts_b = generate_alerts_for_user(uuid.uuid4(), _make_prefs(alert_threshold=0.10), debates)
    assert len(alerts_b) == 0


def test_whale_signals_attached():
    user_id = uuid.uuid4()
    prefs = _make_prefs(alert_threshold=0.05)
    debates = [_make_debate_result(market_id="m1", ai_prob=0.65, poly_price=0.50)]
    whale_data = {"m1": [{"wallet": "0xabc", "side": "BUY", "size": 50000}]}

    alerts = generate_alerts_for_user(user_id, prefs, debates, whale_scan_data=whale_data)
    assert len(alerts) == 1
    assert len(alerts[0].whale_signals) == 1


def test_empty_debates():
    alerts = generate_alerts_for_user(uuid.uuid4(), _make_prefs(), [])
    assert alerts == []
