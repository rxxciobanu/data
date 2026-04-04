"""FastAPI dependency injection — DB session, current user, Redis."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from saas.auth.api_keys import get_prefix_from_key, verify_api_key
from saas.auth.jwt import get_user_id_from_token
from saas.db.engine import get_db_session
from saas.db.queries import get_api_keys_by_prefix, get_user_by_id, touch_api_key

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


async def _get_current_user_id(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
    session: AsyncSession = Depends(get_db_session),
) -> uuid.UUID:
    """Extract and validate user identity from JWT or API key."""

    # Try JWT first
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        user_id = get_user_id_from_token(token, expected_type="access")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
        return user_id

    # Try API key
    if x_api_key:
        prefix = get_prefix_from_key(x_api_key)
        candidates = await get_api_keys_by_prefix(session, prefix)
        for candidate in candidates:
            if verify_api_key(x_api_key, candidate.key_hash):
                await touch_api_key(session, candidate.id)
                return candidate.user_id
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing Authorization header or X-API-Key",
    )


CurrentUserID = Annotated[uuid.UUID, Depends(_get_current_user_id)]


async def get_current_user(
    user_id: CurrentUserID,
    session: DBSession,
):
    """Resolve the full User object for the authenticated user."""
    from saas.db.models import User

    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user
