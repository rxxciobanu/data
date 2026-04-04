"""Tests for whale service — DB state and core engine integration."""
from __future__ import annotations

import uuid


def test_db_whale_state_interface():
    """Verify DBWhaleState has the expected interface."""
    from saas.services.whale_service import DBWhaleState

    # Just check methods exist (can't test DB without async session)
    assert hasattr(DBWhaleState, "get_last_seen")
    assert hasattr(DBWhaleState, "set_last_seen")
    assert hasattr(DBWhaleState, "is_first_run")


def test_whale_scan_result_model():
    """Verify WhaleScanResult ORM model has correct columns."""
    from saas.db.models import WhaleScanResult

    assert hasattr(WhaleScanResult, "cycle_id")
    assert hasattr(WhaleScanResult, "wallet_address")
    assert hasattr(WhaleScanResult, "wallet_label")
    assert hasattr(WhaleScanResult, "wallet_stats")
    assert hasattr(WhaleScanResult, "new_trades")


def test_whale_state_model():
    """Verify WhaleState ORM model has composite primary key."""
    from saas.db.models import WhaleState

    pk_cols = [c.name for c in WhaleState.__table__.primary_key.columns]
    assert "user_id" in pk_cols
    assert "address" in pk_cols


def test_usage_log_model():
    """Verify UsageLog ORM model structure."""
    from saas.db.models import UsageLog

    assert hasattr(UsageLog, "user_id")
    assert hasattr(UsageLog, "event_type")
    assert hasattr(UsageLog, "metadata_")
    assert hasattr(UsageLog, "created_at")
