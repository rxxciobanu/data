"""Database-backed whale state service — replaces JSON file for SaaS.

Per-user whale state tracking: each user has their own last_seen timestamps
so new-user bootstrapping and alert deduplication work correctly in
multi-tenant context.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from saas.db.queries import get_whale_last_seen, upsert_whale_last_seen


class DBWhaleState:
    """Database-backed whale state for a specific user.

    Replaces the JSON-file WhaleState from the core engine.
    """

    def __init__(self, user_id: uuid.UUID, session: AsyncSession):
        self.user_id = user_id
        self.session = session

    async def get_last_seen(self, address: str) -> datetime | None:
        return await get_whale_last_seen(self.session, self.user_id, address)

    async def set_last_seen(self, address: str, last_seen: datetime) -> None:
        await upsert_whale_last_seen(self.session, self.user_id, address, last_seen)

    async def is_first_run(self, address: str) -> bool:
        """Check if this is the first time we've seen this wallet for this user."""
        return (await self.get_last_seen(address)) is None
