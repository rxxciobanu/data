#!/usr/bin/env python3
"""SaaS integration test — runs against the FastAPI app with SQLite in-memory.

No Docker, no PostgreSQL, no Redis needed.
Tests the full user flow: register → login → set preferences → check alerts.
"""
from __future__ import annotations

import asyncio
import os
import sys

# Override database to SQLite before any imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test_saas.db"
os.environ["REDIS_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret-for-local-testing-only"

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} — {detail}")


async def run_tests():
    # Create tables
    from saas.db.engine import get_engine
    from saas.db.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created (SQLite)")

    # Use httpx with FastAPI's TestClient equivalent
    from httpx import ASGITransport, AsyncClient
    from saas.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:

        print("\n" + "=" * 70)
        print("  SAAS API INTEGRATION TESTS")
        print("=" * 70)

        # ── Health ──
        print("\n--- Health Check ---")
        r = await client.get("/api/v1/health")
        check("GET /health → 200", r.status_code == 200)
        check("Health response has status", r.json().get("status") == "ok")

        # ── Register ──
        print("\n--- Auth: Register ---")
        r = await client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "SecurePassword123!",
        })
        check("POST /auth/register → 201", r.status_code == 201, f"got {r.status_code}: {r.text}")
        tokens = r.json()
        check("Register returns access_token", "access_token" in tokens)
        check("Register returns user_id", "user_id" in tokens)
        access_token = tokens.get("access_token", "")
        user_id = tokens.get("user_id", "")

        # ── Duplicate register ──
        r = await client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "AnotherPassword123!",
        })
        check("Duplicate email → 409", r.status_code == 409)

        # ── Short password ──
        r = await client.post("/api/v1/auth/register", json={
            "email": "test2@example.com",
            "password": "short",
        })
        check("Short password → 422", r.status_code == 422)

        # ── Login ──
        print("\n--- Auth: Login ---")
        r = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "SecurePassword123!",
        })
        check("POST /auth/login → 200", r.status_code == 200, f"got {r.status_code}: {r.text}")
        check("Login returns tokens", "access_token" in r.json())

        # ── Wrong password ──
        r = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "WrongPassword!",
        })
        check("Wrong password → 401", r.status_code == 401)

        # ── Auth headers ──
        headers = {"Authorization": f"Bearer {access_token}"}

        # ── Profile ──
        print("\n--- User Profile ---")
        r = await client.get("/api/v1/users/me", headers=headers)
        check("GET /users/me → 200", r.status_code == 200, f"got {r.status_code}: {r.text}")
        profile = r.json()
        check("Profile has email", profile.get("email") == "test@example.com")
        check("Profile has id", profile.get("id") == user_id)

        # ── No auth ──
        r = await client.get("/api/v1/users/me")
        check("No auth → 401", r.status_code == 401)

        # ── Preferences ──
        print("\n--- User Preferences ---")
        r = await client.get("/api/v1/users/me/preferences", headers=headers)
        check("GET /preferences → 200", r.status_code == 200, f"got {r.status_code}: {r.text}")
        prefs = r.json()
        check("Default threshold = 0.10", prefs.get("alert_threshold") == 0.10)
        check("Default bankroll = 0", prefs.get("bankroll") == 0)
        check("Default kelly = 0.25", prefs.get("kelly_fraction") == 0.25)
        check("Default whale disabled", prefs.get("whale_enabled") is False)

        # ── Update preferences ──
        r = await client.put("/api/v1/users/me/preferences", headers=headers, json={
            "bankroll": 5000,
            "alert_threshold": 0.08,
            "whale_enabled": True,
        })
        check("PUT /preferences → 200", r.status_code == 200, f"got {r.status_code}: {r.text}")
        updated = r.json()
        check("Bankroll updated to 5000", updated.get("bankroll") == 5000)
        check("Threshold updated to 0.08", updated.get("alert_threshold") == 0.08)
        check("Whale enabled", updated.get("whale_enabled") is True)

        # ── Invalid preferences ──
        r = await client.put("/api/v1/users/me/preferences", headers=headers, json={
            "alert_threshold": 5.0,  # Must be 0-1
        })
        check("Invalid threshold → 422", r.status_code == 422)

        r = await client.put("/api/v1/users/me/preferences", headers=headers, json={
            "bankroll": -100,  # Must be >= 0
        })
        check("Negative bankroll → 422", r.status_code == 422)

        # ── API Keys ──
        print("\n--- API Keys ---")
        r = await client.post("/api/v1/auth/api-keys", headers=headers, json={
            "label": "My Test Key",
        })
        check("POST /api-keys → 201", r.status_code == 201, f"got {r.status_code}: {r.text}")
        key_data = r.json()
        raw_key = key_data.get("raw_key", "")
        check("API key starts with pm_", raw_key.startswith("pm_"))
        check("API key has label", key_data.get("label") == "My Test Key")

        # ── Use API key for auth ──
        r = await client.get("/api/v1/users/me", headers={"X-API-Key": raw_key})
        check("Auth with API key → 200", r.status_code == 200, f"got {r.status_code}: {r.text}")
        check("API key resolves same user", r.json().get("email") == "test@example.com")

        # ── List API keys ──
        r = await client.get("/api/v1/auth/api-keys", headers=headers)
        check("GET /api-keys → 200", r.status_code == 200)
        check("Has 1 API key", len(r.json()) == 1)

        # ── Alerts (empty — no debate cycle run) ──
        print("\n--- Alerts ---")
        r = await client.get("/api/v1/alerts", headers=headers)
        check("GET /alerts → 200", r.status_code == 200)
        check("No alerts yet", len(r.json()) == 0)

        r = await client.get("/api/v1/alerts/latest", headers=headers)
        check("GET /alerts/latest → 200", r.status_code == 200)

        r = await client.get("/api/v1/alerts/stats", headers=headers)
        check("GET /alerts/stats → 200", r.status_code == 200)
        stats = r.json()
        check("Stats total = 0", stats.get("total_alerts") == 0)

        # ── Markets (empty — no debate cycle) ──
        print("\n--- Markets ---")
        r = await client.get("/api/v1/markets", headers=headers)
        check("GET /markets → 200", r.status_code == 200)
        check("No markets yet", len(r.json()) == 0)

        # ── Whale Config ──
        print("\n--- Whale Config ---")
        r = await client.get("/api/v1/whales/config", headers=headers)
        check("GET /whales/config → 200", r.status_code == 200, f"got {r.status_code}: {r.text}")
        wc = r.json()
        check("Whale enabled (from prefs update)", wc.get("whale_enabled") is True)

        r = await client.put("/api/v1/whales/config", headers=headers, json={
            "whale_min_trade_size": 500,
            "whale_extra_wallets": [{"address": "0xabc123", "label": "Alpha Whale"}],
        })
        check("PUT /whales/config → 200", r.status_code == 200, f"got {r.status_code}: {r.text}")
        check("Min trade size updated", r.json().get("whale_min_trade_size") == 500)

        # ── Token refresh ──
        print("\n--- Token Refresh ---")
        # Login to get a refresh token
        r = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "SecurePassword123!",
        })
        refresh_token = r.json().get("refresh_token", "")

        r = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        check("POST /auth/refresh → 200", r.status_code == 200, f"got {r.status_code}: {r.text}")
        check("Refresh returns new access_token", "access_token" in r.json())

        # ── Second user ──
        print("\n--- Multi-Tenant Isolation ---")
        r = await client.post("/api/v1/auth/register", json={
            "email": "user2@example.com",
            "password": "AnotherSecure123!",
        })
        check("Second user registered", r.status_code == 201)
        user2_token = r.json().get("access_token", "")
        headers2 = {"Authorization": f"Bearer {user2_token}"}

        # User 2 should have default prefs, not user 1's
        r = await client.get("/api/v1/users/me/preferences", headers=headers2)
        prefs2 = r.json()
        check("User 2 has default threshold (0.10)", prefs2.get("alert_threshold") == 0.10)
        check("User 2 bankroll is 0 (not 5000)", prefs2.get("bankroll") == 0)
        check("User 2 whale disabled", prefs2.get("whale_enabled") is False)

        # User 2 can't see user 1's API keys
        r = await client.get("/api/v1/auth/api-keys", headers=headers2)
        check("User 2 has 0 API keys", len(r.json()) == 0)

    # Cleanup
    import os
    os.unlink("test_saas.db") if os.path.exists("test_saas.db") else None

    # Summary
    print("\n" + "=" * 70)
    total = passed + failed
    print(f"  Results: {passed} passed, {failed} failed out of {total} tests")
    if failed == 0:
        print("  All SaaS integration tests passed!")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run_tests())
    sys.exit(0 if ok else 1)
