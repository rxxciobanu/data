"""Main API router — aggregates all route modules."""
from __future__ import annotations

from fastapi import APIRouter

from saas.api.alert_routes import router as alert_router
from saas.api.auth_routes import router as auth_router
from saas.api.market_routes import router as market_router
from saas.api.user_routes import router as user_router
from saas.api.whale_routes import router as whale_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(alert_router)
api_router.include_router(market_router)
api_router.include_router(whale_router)
