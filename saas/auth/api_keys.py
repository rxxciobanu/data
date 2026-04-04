"""API key generation and validation.

Keys are generated as random 32-byte hex strings prefixed with 'pm_'.
The first 8 characters (after prefix) are stored as the prefix for lookup.
The full key is hashed with bcrypt and stored — the raw key is shown
to the user exactly once on creation.
"""
from __future__ import annotations

import secrets

from saas.auth.passwords import hash_password, verify_password


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (raw_key, key_prefix, key_hash) — raw_key shown to user once.
    """
    raw = "pm_" + secrets.token_hex(32)
    prefix = raw[3:11]  # 8 chars after 'pm_'
    hashed = hash_password(raw)
    return raw, prefix, hashed


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    """Verify a raw API key against its stored hash."""
    return verify_password(raw_key, key_hash)


def get_prefix_from_key(raw_key: str) -> str:
    """Extract the lookup prefix from a raw key."""
    if raw_key.startswith("pm_"):
        return raw_key[3:11]
    return raw_key[:8]
