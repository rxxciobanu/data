"""Celery application configuration with Redis broker."""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

# Load .env before settings
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "polymarket_saas",
    broker=redis_url,
    backend=redis_url,
    include=[
        "saas.workers.debate_cycle",
        "saas.workers.fan_out",
        "saas.workers.notify",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Retry on connection loss
    broker_connection_retry_on_startup=True,
)

# Periodic tasks (Celery Beat)
debate_interval = int(os.getenv("DEBATE_CYCLE_INTERVAL", "240"))

app.conf.beat_schedule = {
    "debate-cycle": {
        "task": "saas.workers.debate_cycle.run_cycle",
        "schedule": debate_interval * 60,  # Convert minutes to seconds
        "options": {"queue": "debate"},
    },
}
