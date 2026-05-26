import pytest
from datetime import datetime, timezone, timedelta
from auth.jwt_handler import create_access_token, decode_access_token


def test_round_trip_contains_expected_claims():
    expires_at = datetime(2026, 12, 31, tzinfo=timezone.utc)
    token = create_access_token(42, "full_access", expires_at, "Alice")
    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["role"] == "full_access"
    assert payload["name"] == "Alice"
    assert payload["expires_at"] == expires_at.isoformat()


def test_name_defaults_to_empty_string():
    token = create_access_token(1, "free", None)
    payload = decode_access_token(token)
    assert payload["name"] == ""


def test_expires_at_none_stored_as_none():
    token = create_access_token(1, "free", None)
    payload = decode_access_token(token)
    assert payload["expires_at"] is None


def test_tampered_token_returns_empty_dict():
    token = create_access_token(1, "free", None)
    tampered = token[:-4] + "xxxx"
    assert decode_access_token(tampered) == {}


def test_expired_token_returns_empty_dict():
    import os
    from jose import jwt
    from utils.constants import JWT_ALGORITHM
    secret = os.environ["JWT_SECRET"]
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    token = jwt.encode({"sub": "1", "exp": past}, secret, algorithm=JWT_ALGORITHM)
    assert decode_access_token(token) == {}
