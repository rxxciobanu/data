"""Tests for fan-out logic — threshold filtering at scale."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from saas.services.alert_service import generate_alerts_for_user


def _prefs(**kw):
    p = MagicMock()
    defaults = dict(
        alert_threshold=0.10, alert_enabled=True, bankroll=0,
        kelly_fraction=0.25, max_bet_pct=0.05, max_total_exposure=0.25,
        min_bet_size=5.0, whale_enabled=False, whale_min_trade_size=1000,
    )
    defaults.update(kw)
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


def _debate(market_id, ai, poly, cycle="c1"):
    dr = MagicMock()
    dr.id = uuid.uuid4()
    dr.cycle_id = cycle
    dr.market_id = market_id
    dr.market_question = f"Market {market_id}?"
    dr.polymarket_price = poly
    dr.consensus_probability = ai
    dr.market_data = {
        "id": market_id, "question": f"Market {market_id}?",
        "description": "", "outcomes": ["Yes", "No"],
        "tokens": [
            {"token_id": f"{market_id}-yes", "outcome": "Yes", "price": poly},
            {"token_id": f"{market_id}-no", "outcome": "No", "price": 1 - poly},
        ],
    }
    return dr


def test_fan_out_100_users_10_markets():
    """Simulate fan-out: 100 users × 10 markets with varying thresholds."""
    debates = [
        _debate(f"m{i}", ai=0.50 + (i * 0.03), poly=0.50)  # 3%, 6%, 9%, 12%, ...
        for i in range(1, 11)
    ]

    total_alerts = 0
    for user_idx in range(100):
        # Vary threshold: 5%, 8%, 11%, 14%...
        threshold = 0.05 + (user_idx % 5) * 0.03
        prefs = _prefs(alert_threshold=threshold)
        alerts = generate_alerts_for_user(uuid.uuid4(), prefs, debates)
        total_alerts += len(alerts)

    # With 10 markets and varying thresholds, should generate reasonable alerts
    assert total_alerts > 0
    assert total_alerts < 100 * 10  # Not every user gets every market


def test_fan_out_no_divergence():
    """All markets at same price → no alerts for anyone."""
    debates = [_debate(f"m{i}", ai=0.50, poly=0.50) for i in range(5)]

    for _ in range(100):
        alerts = generate_alerts_for_user(uuid.uuid4(), _prefs(), debates)
        assert len(alerts) == 0


def test_fan_out_high_divergence_all_users_alerted():
    """One market with huge divergence → every user gets an alert."""
    debates = [_debate("m1", ai=0.90, poly=0.50)]  # 40% divergence

    for _ in range(50):
        alerts = generate_alerts_for_user(uuid.uuid4(), _prefs(alert_threshold=0.30), debates)
        assert len(alerts) == 1
        assert alerts[0].recommended_side == "YES"
