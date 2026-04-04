"""Tests for auth module: passwords, JWT, API keys."""
from __future__ import annotations

import uuid

from saas.auth.api_keys import generate_api_key, get_prefix_from_key, verify_api_key
from saas.auth.jwt import create_access_token, create_refresh_token, get_user_id_from_token
from saas.auth.passwords import hash_password, verify_password


def test_password_hash_and_verify():
    plain = "MySecretPassword123!"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("wrong_password", hashed)


def test_password_different_hashes():
    plain = "same_password"
    h1 = hash_password(plain)
    h2 = hash_password(plain)
    assert h1 != h2  # bcrypt uses random salt
    assert verify_password(plain, h1)
    assert verify_password(plain, h2)


def test_jwt_access_token():
    uid = uuid.uuid4()
    token = create_access_token(uid)
    assert isinstance(token, str)
    assert len(token) > 50

    extracted = get_user_id_from_token(token, expected_type="access")
    assert extracted == uid


def test_jwt_refresh_token():
    uid = uuid.uuid4()
    token = create_refresh_token(uid)
    extracted = get_user_id_from_token(token, expected_type="refresh")
    assert extracted == uid

    # Wrong type should fail
    assert get_user_id_from_token(token, expected_type="access") is None


def test_jwt_invalid_token():
    assert get_user_id_from_token("garbage.token.here") is None
    assert get_user_id_from_token("") is None


def test_api_key_generation():
    raw, prefix, hashed = generate_api_key()
    assert raw.startswith("pm_")
    assert len(prefix) == 8
    assert len(raw) == 67  # pm_ + 64 hex chars
    assert verify_api_key(raw, hashed)
    assert not verify_api_key("pm_wrong_key", hashed)


def test_api_key_prefix_extraction():
    raw, prefix, _ = generate_api_key()
    assert get_prefix_from_key(raw) == prefix


def test_api_key_uniqueness():
    keys = {generate_api_key()[0] for _ in range(10)}
    assert len(keys) == 10  # All unique
