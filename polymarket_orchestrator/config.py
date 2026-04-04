from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Email
    smtp_email: str = os.getenv("SMTP_EMAIL", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    alert_recipient: str = os.getenv("ALERT_RECIPIENT", "")

    # Polymarket
    polymarket_host: str = os.getenv("POLYMARKET_HOST", "https://clob.polymarket.com")
    gamma_api_host: str = os.getenv("GAMMA_API_HOST", "https://gamma-api.polymarket.com")

    # Orchestrator
    alert_threshold: float = float(os.getenv("ALERT_THRESHOLD", "0.10"))
    max_markets: int = int(os.getenv("MAX_MARKETS", "10"))

    # Claude model for debate agents
    debate_model: str = "claude-sonnet-4-6"

    # Aggregation method: "extremized", "log_odds", or "weighted_avg"
    aggregation_method: str = os.getenv("AGGREGATION_METHOD", "extremized")

    # Position sizing (Kelly Criterion)
    # Set BANKROLL > 0 to enable bet sizing. $0 = sizing disabled.
    bankroll: float = float(os.getenv("BANKROLL", "0"))
    kelly_fraction: float = float(os.getenv("KELLY_FRACTION", "0.25"))       # Quarter-Kelly
    max_bet_pct: float = float(os.getenv("MAX_BET_PCT", "0.05"))             # 5% per market
    max_total_exposure: float = float(os.getenv("MAX_TOTAL_EXPOSURE", "0.25"))  # 25% total
    min_bet_size: float = float(os.getenv("MIN_BET_SIZE", "5"))              # $5 minimum

    # News integration
    newsdata_api_key: str = os.getenv("NEWSDATA_API_KEY", "")
    news_enabled: bool = os.getenv("NEWS_ENABLED", "true").lower() in ("true", "1", "yes")
    news_max_articles: int = int(os.getenv("NEWS_MAX_ARTICLES", "5"))

    # Whale wallet tracking
    whale_enabled: bool = os.getenv("WHALE_ENABLED", "false").lower() in ("true", "1", "yes")
    whale_leaderboard_count: int = int(os.getenv("WHALE_LEADERBOARD_COUNT", "20"))
    whale_extra_wallets: str = os.getenv("WHALE_EXTRA_WALLETS", "")
    whale_state_path: str = os.getenv("WHALE_STATE_PATH", "~/.polymarket/whale_state.json")
    whale_min_trade_size: float = float(os.getenv("WHALE_MIN_TRADE_SIZE", "1000"))


settings = Settings()
