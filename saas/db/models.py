"""SQLAlchemy ORM models for the SaaS layer.

All tables mirror the schema from the plan:
- users, api_keys, user_preferences (auth + config)
- debate_results (shared), user_alerts (per-user)
- whale_state (per-user), whale_scan_results (shared)
- usage_log (metering)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Users & Auth
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    preferences: Mapped[UserPreferences | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    api_keys: Mapped[list[ApiKey]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alerts: Mapped[list[UserAlert]] = relationship(back_populates="user", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys")


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("alert_threshold >= 0 AND alert_threshold <= 1", name="ck_alert_threshold"),
        CheckConstraint("bankroll >= 0", name="ck_bankroll"),
        CheckConstraint("kelly_fraction >= 0.01 AND kelly_fraction <= 1", name="ck_kelly_fraction"),
        CheckConstraint("max_bet_pct >= 0.01 AND max_bet_pct <= 1", name="ck_max_bet_pct"),
        CheckConstraint("max_total_exposure >= 0.01 AND max_total_exposure <= 1", name="ck_max_total_exposure"),
        CheckConstraint("min_bet_size >= 0", name="ck_min_bet_size"),
        CheckConstraint("whale_min_trade_size >= 0", name="ck_whale_min_trade_size"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    # Alert config
    alert_threshold: Mapped[float] = mapped_column(Float, default=0.10)
    alert_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Position sizing
    bankroll: Mapped[float] = mapped_column(Float, default=0.0)
    kelly_fraction: Mapped[float] = mapped_column(Float, default=0.25)
    max_bet_pct: Mapped[float] = mapped_column(Float, default=0.05)
    max_total_exposure: Mapped[float] = mapped_column(Float, default=0.25)
    min_bet_size: Mapped[float] = mapped_column(Float, default=5.0)

    # Notifications
    notification_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Whale config
    whale_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    whale_min_trade_size: Mapped[float] = mapped_column(Float, default=1000.0)
    whale_extra_wallets: Mapped[dict] = mapped_column(JSON, default=list)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped[User] = relationship(back_populates="preferences")


# ---------------------------------------------------------------------------
# Debate Results (SHARED — one per market per cycle)
# ---------------------------------------------------------------------------


class DebateResult(Base):
    __tablename__ = "debate_results"
    __table_args__ = (
        UniqueConstraint("cycle_id", "market_id", name="uq_debate_cycle_market"),
        Index("idx_debate_cycle", "cycle_id"),
        Index("idx_debate_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    cycle_id: Mapped[str] = mapped_column(String(50), nullable=False)
    market_id: Mapped[str] = mapped_column(String(255), nullable=False)
    market_question: Mapped[str] = mapped_column(Text, nullable=False)
    market_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    opinions: Mapped[list] = mapped_column(JSON, nullable=False)
    consensus_probability: Mapped[float] = mapped_column(Float, nullable=False)
    synthesis_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    polymarket_price: Mapped[float] = mapped_column(Float, nullable=False)
    news_articles: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# User Alerts (PER-USER — generated from shared debate results)
# ---------------------------------------------------------------------------


class UserAlert(Base):
    __tablename__ = "user_alerts"
    __table_args__ = (
        Index("idx_alerts_user", "user_id", "created_at"),
        Index("idx_alerts_cycle", "cycle_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    debate_result_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("debate_results.id"), nullable=True)
    cycle_id: Mapped[str] = mapped_column(String(50), nullable=False)
    market_id: Mapped[str] = mapped_column(String(255), nullable=False)
    market_question: Mapped[str] = mapped_column(Text, nullable=False)
    polymarket_probability: Mapped[float] = mapped_column(Float, nullable=False)
    ai_probability: Mapped[float] = mapped_column(Float, nullable=False)
    divergence: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_side: Mapped[str] = mapped_column(String(3), nullable=False)

    # Per-user Kelly sizing
    bet_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sizing_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Whale signals
    whale_signals: Mapped[list] = mapped_column(JSON, default=list)

    # Delivery tracking
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notification_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="alerts")


# ---------------------------------------------------------------------------
# Whale State (per-user — replaces JSON file)
# ---------------------------------------------------------------------------


class WhaleState(Base):
    __tablename__ = "whale_state"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    address: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WhaleScanResult(Base):
    __tablename__ = "whale_scan_results"
    __table_args__ = (
        UniqueConstraint("cycle_id", "wallet_address", name="uq_whale_cycle_wallet"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    cycle_id: Mapped[str] = mapped_column(String(50), nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(255), nullable=False)
    wallet_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    wallet_stats: Mapped[dict] = mapped_column(JSON, nullable=False)
    new_trades: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Usage Tracking (future billing)
# ---------------------------------------------------------------------------


class UsageLog(Base):
    __tablename__ = "usage_log"
    __table_args__ = (
        Index("idx_usage_user_date", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
