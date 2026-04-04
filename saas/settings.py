"""SaaS-specific configuration.

Separate from polymarket_orchestrator.config which handles CLI settings.
The SaaS app reads its own environment variables for infrastructure config
while importing the core engine library directly.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class SaaSSettings(BaseSettings):
    """SaaS infrastructure settings — loaded from environment variables."""

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://polymarket:polymarket@localhost:5432/polymarket",
        alias="DATABASE_URL",
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # JWT
    jwt_secret: str = Field(default="CHANGE-ME-IN-PRODUCTION", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # CORS
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    # Debate cycle
    debate_cycle_interval_minutes: int = Field(default=240, alias="DEBATE_CYCLE_INTERVAL")
    debate_market_limit: int = Field(default=100, alias="DEBATE_MARKET_LIMIT")
    debate_concurrency: int = Field(default=5, alias="DEBATE_CONCURRENCY")

    # Email (SaaS sends from a platform account)
    smtp_host: str = Field(default="smtp.gmail.com", alias="SAAS_SMTP_HOST")
    smtp_port: int = Field(default=465, alias="SAAS_SMTP_PORT")
    smtp_email: str = Field(default="", alias="SAAS_SMTP_EMAIL")
    smtp_password: str = Field(default="", alias="SAAS_SMTP_PASSWORD")
    smtp_from_name: str = Field(default="Polymarket AI", alias="SAAS_SMTP_FROM_NAME")

    # Rate limiting
    rate_limit_per_minute: int = 100
    auth_rate_limit_per_minute: int = 10

    # Anthropic (for debate agents — shared across all users)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # News
    newsdata_api_key: str = Field(default="", alias="NEWSDATA_API_KEY")
    news_enabled: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> SaaSSettings:
    return SaaSSettings()
