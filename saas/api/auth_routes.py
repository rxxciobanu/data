"""Auth endpoints: register, login, refresh, API key management."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from saas.auth.api_keys import generate_api_key
from saas.auth.jwt import create_access_token, create_refresh_token, get_user_id_from_token
from saas.auth.passwords import hash_password, verify_password
from saas.db.engine import get_db_session
from saas.db.queries import (
    create_api_key,
    create_user,
    deactivate_api_key,
    get_user_api_keys,
    get_user_by_email,
)
from saas.deps import CurrentUserID

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID


class RefreshRequest(BaseModel):
    refresh_token: str


class ApiKeyCreate(BaseModel):
    label: str = Field(default="", max_length=100)


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    key_prefix: str
    label: str
    created_at: str
    last_used: str | None = None
    # raw_key only returned on creation
    raw_key: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_db_session)):
    existing = await get_user_by_email(session, body.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = await create_user(session, email=body.email, password_hash=hash_password(body.password))
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db_session)):
    user = await get_user_by_email(session, body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_db_session)):
    user_id = get_user_id_from_token(body.refresh_token, expected_type="refresh")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    from saas.db.queries import get_user_by_id

    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
    )


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreate,
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    raw_key, prefix, key_hash = generate_api_key()
    key = await create_api_key(session, user_id=user_id, key_hash=key_hash, key_prefix=prefix, label=body.label)
    return ApiKeyResponse(
        id=key.id,
        key_prefix=prefix,
        label=key.label,
        created_at=key.created_at.isoformat(),
        raw_key=raw_key,  # Shown once!
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_keys(
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    keys = await get_user_api_keys(session, user_id)
    return [
        ApiKeyResponse(
            id=k.id,
            key_prefix=k.key_prefix,
            label=k.label,
            created_at=k.created_at.isoformat(),
            last_used=k.last_used.isoformat() if k.last_used else None,
        )
        for k in keys
        if k.is_active
    ]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    key_id: uuid.UUID,
    user_id: CurrentUserID,
    session: AsyncSession = Depends(get_db_session),
):
    deleted = await deactivate_api_key(session, key_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
