"""Password hashing with bcrypt directly (no passlib)."""
from __future__ import annotations

import hashlib

import bcrypt


def _prehash(plain: str) -> bytes:
    """Pre-hash with SHA-256 to handle passwords > 72 bytes.

    bcrypt truncates at 72 bytes; pre-hashing with SHA-256
    produces a fixed 64-char hex string (always < 72 bytes).
    """
    encoded = plain.encode("utf-8")
    if len(encoded) <= 72:
        return encoded
    return hashlib.sha256(encoded).hexdigest().encode("utf-8")


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(_prehash(plain), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
