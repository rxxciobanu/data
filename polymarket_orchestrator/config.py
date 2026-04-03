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


settings = Settings()
