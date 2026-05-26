import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from services.auth_service import register_user, login_user, hash_password, verify_password


# ── password helpers ──────────────────────────────────────────────────────────

def test_hash_and_verify_roundtrip():
    hashed = hash_password("Secret123")
    assert verify_password("Secret123", hashed)
    assert not verify_password("wrong", hashed)


# ── register_user ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_user(id=1, name="Alice", email="a@example.com", role="free",
               password_hash="hash", expires_at=None):
    u = MagicMock()
    u.id = id
    u.name = name
    u.email = email
    u.role = role
    u.password_hash = password_hash
    u.expires_at = expires_at
    return u


def _make_request(id=10, reference_id="ref-uuid"):
    r = MagicMock()
    r.id = id
    r.reference_id = reference_id
    return r


@pytest.mark.asyncio
async def test_register_user_password_mismatch_raises_400(mock_db):
    expires = datetime(2026, 12, 31, tzinfo=timezone.utc)
    with pytest.raises(HTTPException) as exc:
        await register_user(mock_db, "a@b.com", "Alice", "pass1", "pass2", "full_access", expires)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_register_user_duplicate_email_raises_409(mock_db):
    expires = datetime(2026, 12, 31, tzinfo=timezone.utc)
    with patch("services.auth_service.get_user_by_email", AsyncMock(return_value=_make_user())):
        with pytest.raises(HTTPException) as exc:
            await register_user(mock_db, "a@b.com", "Alice", "pass", "pass", "full_access", expires)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_register_user_happy_path_returns_reference_id(mock_db):
    expires = datetime(2026, 12, 31, tzinfo=timezone.utc)
    user = _make_user()
    req = _make_request(reference_id="test-ref-123")

    with patch("services.auth_service.get_user_by_email", AsyncMock(return_value=None)), \
         patch("services.auth_service.create_user", AsyncMock(return_value=user)), \
         patch("services.auth_service.create_access_request", AsyncMock(return_value=req)), \
         patch("services.auth_service.insert_audit_log", AsyncMock()):
        result = await register_user(mock_db, "a@b.com", "Alice", "pass", "pass", "full_access", expires)

    assert result["reference_id"] == "test-ref-123"


# ── login_user ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_user_wrong_password_returns_none(mock_db):
    hashed = hash_password("correct")
    user = _make_user(password_hash=hashed)

    with patch("services.auth_service.get_user_by_email", AsyncMock(return_value=user)):
        result = await login_user(mock_db, "a@b.com", "wrong")
    assert result is None


@pytest.mark.asyncio
async def test_login_user_unknown_email_returns_none(mock_db):
    with patch("services.auth_service.get_user_by_email", AsyncMock(return_value=None)):
        result = await login_user(mock_db, "nobody@x.com", "pass")
    assert result is None


@pytest.mark.asyncio
async def test_login_user_success_returns_token(mock_db):
    hashed = hash_password("correct")
    user = _make_user(password_hash=hashed, role="full_access")

    with patch("services.auth_service.get_user_by_email", AsyncMock(return_value=user)), \
         patch("services.auth_service.create_api_token", AsyncMock()):
        result = await login_user(mock_db, "a@b.com", "correct")

    assert result is not None
    assert "access_token" in result
    assert result["token_type"] == "bearer"
