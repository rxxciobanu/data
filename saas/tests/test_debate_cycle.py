"""Tests for debate service — verifying core engine integration."""
from __future__ import annotations

from saas.services.alert_service import GeneratedAlert


def test_generated_alert_creation():
    """Verify GeneratedAlert dataclass construction."""
    import uuid

    alert = GeneratedAlert(
        user_id=uuid.uuid4(),
        debate_result_id=uuid.uuid4(),
        cycle_id="2026-04-04T12:00:00Z",
        market_id="test-market-1",
        market_question="Will it rain tomorrow?",
        polymarket_probability=0.40,
        ai_probability=0.65,
        divergence=0.25,
        recommended_side="YES",
        bet_amount=500.0,
        sizing_details={"kelly_raw": 0.15, "kelly_final": 0.04},
    )

    assert alert.divergence == 0.25
    assert alert.recommended_side == "YES"
    assert alert.bet_amount == 500.0


def test_settings_load():
    """Verify SaaS settings load without error."""
    from saas.settings import SaaSSettings

    settings = SaaSSettings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        redis_url="redis://localhost:6379/0",
        jwt_secret="test-secret-key-for-testing-only",
    )
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_token_expire_minutes == 15
    assert settings.debate_cycle_interval_minutes == 240
    assert settings.cors_origin_list == ["*"]


def test_settings_cors_parsing():
    """Verify CORS origin parsing logic."""
    from saas.settings import SaaSSettings

    # Test the parsing method directly on a settings instance
    settings = SaaSSettings()
    # Manually override cors_origins to test parsing
    settings.cors_origins = "http://localhost:3000, http://localhost:8000, https://app.example.com"
    assert len(settings.cors_origin_list) == 3
    assert "http://localhost:3000" in settings.cors_origin_list
