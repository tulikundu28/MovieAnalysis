import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from fastapi import HTTPException
from services.access_service import (
    submit_access_request,
    review_access_request,
    revoke_access_request,
    cancel_own_request,
    fetch_access_requests,
    ROLE_APPROVER_MAP,
    MOVIE_CUSTOMER_ROLES,
    WORKFLOW_ROLES,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_request(id=1, reference_id="ref-1", requester_id=10,
                  requested_role="full_access", status="pending",
                  requested_expires_at=None, review_comment=None):
    r = MagicMock()
    r.id = id
    r.reference_id = reference_id
    r.requester_id = requester_id
    r.requested_role = requested_role
    r.status = status
    r.requested_expires_at = requested_expires_at or datetime(2026, 12, 31, tzinfo=timezone.utc)
    r.review_comment = review_comment
    r._mapping = {
        "id": id, "reference_id": reference_id, "requester_id": requester_id,
        "requested_role": requested_role, "status": status,
    }
    return r


def _make_user(id=10, name="Alice"):
    u = MagicMock()
    u.id = id
    u.name = name
    return u


# ── ROLE_APPROVER_MAP ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("role,expected_approver", [
    ("full_access",   "manager"),
    ("movie_admin",   "workflow_admin"),
    ("manager",       "workflow_admin"),
    ("workflow_admin","workflow_admin"),
])
def test_role_approver_map(role, expected_approver):
    assert ROLE_APPROVER_MAP[role] == expected_approver


def test_movie_customer_roles():
    assert MOVIE_CUSTOMER_ROLES == {"full_access", "movie_admin"}


def test_workflow_roles():
    assert WORKFLOW_ROLES == {"manager", "workflow_admin"}


# ── submit_access_request ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_invalid_role_raises_400(mock_db):
    with pytest.raises(HTTPException) as exc:
        await submit_access_request(mock_db, 1, "manager", "reason",
                                    datetime(2026, 12, 31, tzinfo=timezone.utc))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_submit_duplicate_pending_raises_409(mock_db):
    existing = _make_request()
    with patch("services.access_service.get_pending_request_for_user", AsyncMock(return_value=existing)):
        with pytest.raises(HTTPException) as exc:
            await submit_access_request(mock_db, 1, "full_access", "reason",
                                        datetime(2026, 12, 31, tzinfo=timezone.utc))
    assert exc.value.status_code == 409
    assert exc.value.detail["reference_id"] == "ref-1"


@pytest.mark.asyncio
async def test_submit_happy_path(mock_db):
    req = _make_request()
    with patch("services.access_service.get_pending_request_for_user", AsyncMock(return_value=None)), \
         patch("services.access_service.create_access_request", AsyncMock(return_value=req)), \
         patch("services.access_service.insert_audit_log", AsyncMock()):
        result = await submit_access_request(mock_db, 1, "full_access", "reason",
                                             datetime(2026, 12, 31, tzinfo=timezone.utc))
    assert result["reference_id"] == "ref-1"
    mock_db.commit.assert_awaited_once()


# ── review_access_request ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_not_found_raises_404(mock_db):
    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await review_access_request(mock_db, "bad-ref", 1, "manager", "approved", None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_review_already_reviewed_raises_409(mock_db):
    req = _make_request(status="approved")
    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)):
        with pytest.raises(HTTPException) as exc:
            await review_access_request(mock_db, "ref-1", 1, "manager", "approved", None)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_review_wrong_approver_raises_403(mock_db):
    # full_access requires manager, not workflow_admin
    req = _make_request(requested_role="full_access", status="pending")
    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)):
        with pytest.raises(HTTPException) as exc:
            await review_access_request(mock_db, "ref-1", 1, "workflow_admin", "approved", None)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_review_deny_without_comment_raises_400(mock_db):
    req = _make_request(requested_role="full_access", status="pending")
    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)):
        with pytest.raises(HTTPException) as exc:
            await review_access_request(mock_db, "ref-1", 1, "manager", "denied", None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_review_approve_issues_token(mock_db):
    req = _make_request(requested_role="full_access", status="pending")
    updated = _make_request(status="approved")
    user = _make_user()

    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)), \
         patch("services.access_service.update_access_request", AsyncMock(return_value=updated)), \
         patch("services.access_service.update_user_role", AsyncMock()), \
         patch("services.access_service.get_user_by_id", AsyncMock(return_value=user)), \
         patch("services.access_service.create_api_token", AsyncMock()), \
         patch("services.access_service.insert_audit_log", AsyncMock()):
        result = await review_access_request(mock_db, "ref-1", 1, "manager", "approved", None)

    assert "api_token" in result


@pytest.mark.asyncio
async def test_review_deny_with_comment_succeeds(mock_db):
    req = _make_request(requested_role="full_access", status="pending")
    updated = _make_request(status="denied")

    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)), \
         patch("services.access_service.update_access_request", AsyncMock(return_value=updated)), \
         patch("services.access_service.insert_audit_log", AsyncMock()):
        result = await review_access_request(mock_db, "ref-1", 1, "manager", "denied", "Not eligible")

    assert result["status"] == "denied"
    mock_db.commit.assert_awaited_once()


# ── revoke_access_request ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_non_approved_raises_409(mock_db):
    req = _make_request(status="pending")
    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)):
        with pytest.raises(HTTPException) as exc:
            await revoke_access_request(mock_db, "ref-1", 1, "manager", "reason")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_revoke_wrong_approver_raises_403(mock_db):
    # full_access approved → only manager can revoke
    req = _make_request(requested_role="full_access", status="approved")
    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)):
        with pytest.raises(HTTPException) as exc:
            await revoke_access_request(mock_db, "ref-1", 1, "workflow_admin", "reason")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_revoke_happy_path_downgrades_user(mock_db):
    req = _make_request(requested_role="full_access", status="approved")
    updated = _make_request(status="revoked")

    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)), \
         patch("services.access_service.update_access_request", AsyncMock(return_value=updated)), \
         patch("services.access_service.update_user_role", AsyncMock()) as mock_update_role, \
         patch("services.access_service.revoke_user_tokens", AsyncMock()), \
         patch("services.access_service.insert_audit_log", AsyncMock()):
        await revoke_access_request(mock_db, "ref-1", 1, "manager", "reason")

    mock_update_role.assert_awaited_once_with(mock_db, req.requester_id, "free", None)


# ── cancel_own_request ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_not_found_raises_404(mock_db):
    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await cancel_own_request(mock_db, "bad-ref", 10)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cancel_wrong_requester_raises_403(mock_db):
    req = _make_request(requester_id=10, status="pending")
    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)):
        with pytest.raises(HTTPException) as exc:
            await cancel_own_request(mock_db, "ref-1", 99)  # different user
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_cancel_non_pending_raises_409(mock_db):
    req = _make_request(requester_id=10, status="approved")
    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)):
        with pytest.raises(HTTPException) as exc:
            await cancel_own_request(mock_db, "ref-1", 10)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_cancel_happy_path(mock_db):
    req = _make_request(requester_id=10, status="pending")
    updated = _make_request(status="cancelled")

    with patch("services.access_service.get_access_request_by_reference_id", AsyncMock(return_value=req)), \
         patch("services.access_service.cancel_access_request", AsyncMock(return_value=updated)), \
         patch("services.access_service.insert_audit_log", AsyncMock()):
        result = await cancel_own_request(mock_db, "ref-1", 10)

    assert result["status"] == "cancelled"


# ── fetch_access_requests queue filter ───────────────────────────────────────

@pytest.mark.asyncio
async def test_manager_queue_contains_only_full_access(mock_db):
    with patch("services.access_service.get_access_requests", AsyncMock(return_value=[])) as mock_get:
        await fetch_access_requests(mock_db, "manager")
    _, kwargs = mock_get.call_args
    roles = mock_get.call_args[0][2]
    assert roles == ["full_access"]


@pytest.mark.asyncio
async def test_workflow_admin_queue_excludes_full_access(mock_db):
    with patch("services.access_service.get_access_requests", AsyncMock(return_value=[])) as mock_get:
        await fetch_access_requests(mock_db, "workflow_admin")
    roles = mock_get.call_args[0][2]
    assert "full_access" not in roles
    assert set(roles) == {"movie_admin", "manager", "workflow_admin"}
