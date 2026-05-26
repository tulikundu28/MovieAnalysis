import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from services.workflow_service import register_workflow_user


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_user(id=5):
    u = MagicMock()
    u.id = id
    return u


def _make_request(id=20):
    r = MagicMock()
    r.id = id
    return r


@pytest.mark.asyncio
async def test_invalid_role_raises_400(mock_db):
    with pytest.raises(HTTPException) as exc:
        await register_workflow_user(mock_db, "a@b.com", "Bob", "pass", "pass", "full_access", "reason")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_password_mismatch_raises_400(mock_db):
    with pytest.raises(HTTPException) as exc:
        await register_workflow_user(mock_db, "a@b.com", "Bob", "pass1", "pass2", "manager", "reason")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_email_raises_409(mock_db):
    with patch("services.workflow_service.get_user_by_email", AsyncMock(return_value=_make_user())):
        with pytest.raises(HTTPException) as exc:
            await register_workflow_user(mock_db, "a@b.com", "Bob", "pass", "pass", "manager", "reason")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["manager", "workflow_admin"])
async def test_valid_roles_succeed(mock_db, role):
    user = _make_user()
    req = _make_request()
    with patch("services.workflow_service.get_user_by_email", AsyncMock(return_value=None)), \
         patch("services.workflow_service.create_user", AsyncMock(return_value=user)), \
         patch("services.workflow_service.create_access_request", AsyncMock(return_value=req)), \
         patch("services.workflow_service.insert_audit_log", AsyncMock()):
        result = await register_workflow_user(mock_db, "a@b.com", "Bob", "pass", "pass", role, "reason")
    assert "request_id" in result


@pytest.mark.asyncio
async def test_happy_path_creates_workflow_approver(mock_db):
    user = _make_user()
    req = _make_request()
    with patch("services.workflow_service.get_user_by_email", AsyncMock(return_value=None)), \
         patch("services.workflow_service.create_user", AsyncMock(return_value=user)) as mock_create, \
         patch("services.workflow_service.create_access_request", AsyncMock(return_value=req)), \
         patch("services.workflow_service.insert_audit_log", AsyncMock()):
        await register_workflow_user(mock_db, "a@b.com", "Bob", "pass", "pass", "manager", "reason")
    mock_create.assert_awaited_once()
    _, kwargs = mock_create.call_args
    assert kwargs.get("user_type") == "workflow_approver"
