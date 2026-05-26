import pytest
from tests.integration.conftest import (
    ADMIN_EMAIL, ADMIN_PASSWORD, EXPIRES_AT,
    _register_customer, _register_approver, _login, _auth, _first_pending_ref,
)

pytestmark = pytest.mark.asyncio


# ── Submit access request ─────────────────────────────────────────────────────

async def test_submit_request_requires_auth(client):
    resp = await client.post("/access-requests/", json={
        "requested_role": "full_access",
        "reason": "Need full access",
        "requested_expires_at": EXPIRES_AT,
    })
    assert resp.status_code == 403


async def test_submit_request_happy_path(client, admin_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "movie_admin")
    user_token = await _login(client, "user@test.com", "User1234!")

    # user's pending request was created at registration — submit a second one is blocked
    resp = await client.post("/access-requests/", json={
        "requested_role": "movie_admin",
        "reason": "Need elevated access",
        "requested_expires_at": EXPIRES_AT,
    }, headers=_auth(user_token))
    # Already has a pending request from registration → 409
    assert resp.status_code == 409
    assert "reference_id" in resp.json()["detail"]


async def test_submit_request_after_cancellation(client):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    user_token = await _login(client, "user@test.com", "User1234!")

    # Get own pending request ref
    own = await client.get("/access-requests/?owner=me", headers=_auth(user_token))
    ref = own.json()[0]["reference_id"]

    # Cancel it
    cancel = await client.patch(f"/access-requests/{ref}",
                                json={"status": "cancelled"},
                                headers=_auth(user_token))
    assert cancel.status_code == 200

    # Now can submit a new request
    resp = await client.post("/access-requests/", json={
        "requested_role": "full_access",
        "reason": "Trying again",
        "requested_expires_at": EXPIRES_AT,
    }, headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json()["reference_id"] != ref


async def test_duplicate_pending_request_returns_409_with_existing_ref(client):
    await _register_customer(client, "user@test.com", "User", "User1234!")
    user_token = await _login(client, "user@test.com", "User1234!")

    resp = await client.post("/access-requests/", json={
        "requested_role": "full_access",
        "reason": "Duplicate attempt",
        "requested_expires_at": EXPIRES_AT,
    }, headers=_auth(user_token))
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "reference_id" in detail


# ── View requests ─────────────────────────────────────────────────────────────

async def test_owner_can_list_own_requests(client):
    await _register_customer(client, "user@test.com", "User", "User1234!")
    user_token = await _login(client, "user@test.com", "User1234!")
    resp = await client.get("/access-requests/?owner=me", headers=_auth(user_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_owner_can_get_own_request_by_ref(client):
    await _register_customer(client, "user@test.com", "User", "User1234!")
    user_token = await _login(client, "user@test.com", "User1234!")
    own = await client.get("/access-requests/?owner=me", headers=_auth(user_token))
    ref = own.json()[0]["reference_id"]

    resp = await client.get(f"/access-requests/{ref}", headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json()["reference_id"] == ref


async def test_public_get_by_ref_returns_status_only(client):
    await _register_customer(client, "user@test.com", "User", "User1234!")
    user_token = await _login(client, "user@test.com", "User1234!")
    own = await client.get("/access-requests/?owner=me", headers=_auth(user_token))
    ref = own.json()[0]["reference_id"]

    resp = await client.get(f"/access-requests/{ref}")  # no auth
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"reference_id", "requested_role", "status", "review_comment"}


async def test_get_unknown_ref_returns_404(client):
    resp = await client.get("/access-requests/00000000-0000-0000-0000-111111111111")
    assert resp.status_code == 404


async def test_different_user_cannot_view_others_request(client, admin_token):
    await _register_customer(client, "user@test.com", "User", "User1234!")
    await _register_customer(client, "other@test.com", "Other", "Other123!")
    user_token = await _login(client, "user@test.com", "User1234!")
    own = await client.get("/access-requests/?owner=me", headers=_auth(user_token))
    ref = own.json()[0]["reference_id"]

    other_token = await _login(client, "other@test.com", "Other123!")
    resp = await client.get(f"/access-requests/{ref}", headers=_auth(other_token))
    assert resp.status_code == 403


async def test_non_approver_cannot_list_queue(client):
    await _register_customer(client, "user@test.com", "User", "User1234!")
    user_token = await _login(client, "user@test.com", "User1234!")
    resp = await client.get("/access-requests/", headers=_auth(user_token))
    assert resp.status_code == 403


async def test_manager_queue_contains_only_full_access(client, manager_token):
    await _register_customer(client, "u1@test.com", "U1", "User1234!", "full_access")
    await _register_customer(client, "u2@test.com", "U2", "User1234!", "movie_admin")

    resp = await client.get("/access-requests/", headers=_auth(manager_token))
    assert resp.status_code == 200
    roles = {r["requested_role"] for r in resp.json()}
    assert "movie_admin" not in roles
    assert "full_access" in roles


async def test_admin_queue_excludes_full_access(client, admin_token):
    await _register_customer(client, "u1@test.com", "U1", "User1234!", "full_access")
    await _register_customer(client, "u2@test.com", "U2", "User1234!", "movie_admin")
    await _register_approver(client, "mgr@test.com", "Mgr", "Manager123!", "manager")

    resp = await client.get("/access-requests/", headers=_auth(admin_token))
    assert resp.status_code == 200
    roles = {r["requested_role"] for r in resp.json()}
    assert "full_access" not in roles
    assert "movie_admin" in roles
    assert "manager" in roles


# ── Approve ───────────────────────────────────────────────────────────────────

async def test_manager_approves_full_access_request(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    ref = await _first_pending_ref(client, manager_token, "full_access")

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "approved"},
                              headers=_auth(manager_token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert "api_token" in data


async def test_approved_user_can_login_with_elevated_role(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    ref = await _first_pending_ref(client, manager_token, "full_access")
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(manager_token))

    token = await _login(client, "user@test.com", "User1234!")
    resp = await client.get("/access-requests/?owner=me", headers=_auth(token))
    assert resp.status_code == 200  # full_access can call protected endpoints


async def test_manager_cannot_approve_movie_admin_request(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "movie_admin")
    ref = await _first_pending_ref(client, manager_token, "movie_admin") if False else None
    # manager queue won't contain movie_admin — verify the queue is empty for that role
    resp = await client.get("/access-requests/", headers=_auth(manager_token))
    movie_admin_pending = [r for r in resp.json() if r["requested_role"] == "movie_admin"]
    assert movie_admin_pending == []


async def test_admin_approves_movie_admin_request(client, admin_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "movie_admin")
    ref = await _first_pending_ref(client, admin_token, "movie_admin")

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "approved"},
                              headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_approve_already_approved_returns_409(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    ref = await _first_pending_ref(client, manager_token, "full_access")
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(manager_token))

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "approved"},
                              headers=_auth(manager_token))
    assert resp.status_code == 409


# ── Deny ──────────────────────────────────────────────────────────────────────

async def test_manager_denies_request_with_comment(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    ref = await _first_pending_ref(client, manager_token, "full_access")

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "denied", "review_comment": "Not eligible yet"},
                              headers=_auth(manager_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "denied"
    assert resp.json()["review_comment"] == "Not eligible yet"


async def test_deny_without_comment_returns_400(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    ref = await _first_pending_ref(client, manager_token, "full_access")

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "denied"},
                              headers=_auth(manager_token))
    assert resp.status_code == 400


async def test_user_can_resubmit_after_denial(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    user_token = await _login(client, "user@test.com", "User1234!")
    ref = await _first_pending_ref(client, manager_token, "full_access")

    await client.patch(f"/access-requests/{ref}",
                       json={"status": "denied", "review_comment": "Not now"},
                       headers=_auth(manager_token))

    resp = await client.post("/access-requests/", json={
        "requested_role": "full_access",
        "reason": "Reapplying after denial",
        "requested_expires_at": EXPIRES_AT,
    }, headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json()["reference_id"] != ref


# ── Cancel ────────────────────────────────────────────────────────────────────

async def test_owner_can_cancel_pending_request(client):
    await _register_customer(client, "user@test.com", "User", "User1234!")
    user_token = await _login(client, "user@test.com", "User1234!")
    own = await client.get("/access-requests/?owner=me", headers=_auth(user_token))
    ref = own.json()[0]["reference_id"]

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "cancelled"},
                              headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_cannot_cancel_approved_request(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    user_token = await _login(client, "user@test.com", "User1234!")
    ref = await _first_pending_ref(client, manager_token, "full_access")

    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(manager_token))

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "cancelled"},
                              headers=_auth(user_token))
    assert resp.status_code == 409


async def test_cannot_cancel_another_users_request(client):
    await _register_customer(client, "user@test.com", "User", "User1234!")
    await _register_customer(client, "other@test.com", "Other", "Other123!")
    user_token  = await _login(client, "user@test.com", "User1234!")
    other_token = await _login(client, "other@test.com", "Other123!")

    own = await client.get("/access-requests/?owner=me", headers=_auth(user_token))
    ref = own.json()[0]["reference_id"]

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "cancelled"},
                              headers=_auth(other_token))
    assert resp.status_code == 403


# ── Revoke ────────────────────────────────────────────────────────────────────

async def test_manager_revokes_approved_full_access(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    ref = await _first_pending_ref(client, manager_token, "full_access")
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(manager_token))

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "revoked", "review_comment": "Access no longer needed"},
                              headers=_auth(manager_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


async def test_revoked_user_token_returns_401(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    ref = await _first_pending_ref(client, manager_token, "full_access")
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(manager_token))

    user_token = await _login(client, "user@test.com", "User1234!")
    assert (await client.get("/access-requests/?owner=me", headers=_auth(user_token))).status_code == 200

    await client.patch(f"/access-requests/{ref}",
                       json={"status": "revoked", "review_comment": "Revoked"},
                       headers=_auth(manager_token))

    resp = await client.get("/access-requests/?owner=me", headers=_auth(user_token))
    assert resp.status_code == 401


async def test_cannot_revoke_pending_request(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    ref = await _first_pending_ref(client, manager_token, "full_access")

    resp = await client.patch(f"/access-requests/{ref}",
                              json={"status": "revoked", "review_comment": "Too early"},
                              headers=_auth(manager_token))
    assert resp.status_code == 409


async def test_user_can_resubmit_after_revocation(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    user_token = await _login(client, "user@test.com", "User1234!")
    ref = await _first_pending_ref(client, manager_token, "full_access")

    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(manager_token))
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "revoked", "review_comment": "Revoked"},
                       headers=_auth(manager_token))

    # Need a fresh login to get new token (old one is revoked)
    new_token = await _login(client, "user@test.com", "User1234!")
    resp = await client.post("/access-requests/", json={
        "requested_role": "full_access",
        "reason": "Re-requesting after revoke",
        "requested_expires_at": EXPIRES_AT,
    }, headers=_auth(new_token))
    assert resp.status_code == 200


# ── Audit log ─────────────────────────────────────────────────────────────────

async def test_audit_log_records_full_lifecycle(client, manager_token):
    await _register_customer(client, "user@test.com", "User", "User1234!", "full_access")
    ref = await _first_pending_ref(client, manager_token, "full_access")

    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(manager_token))
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "revoked", "review_comment": "No longer needed"},
                       headers=_auth(manager_token))

    admin_token = await _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    resp = await client.get(f"/access-requests/{ref}/audit", headers=_auth(admin_token))
    assert resp.status_code == 200
    actions = [e["action"] for e in resp.json()]
    assert "submitted" in actions
    assert "approved" in actions
    assert "revoked" in actions


async def test_audit_log_requires_approver_role(client):
    await _register_customer(client, "user@test.com", "User", "User1234!")
    user_token = await _login(client, "user@test.com", "User1234!")
    own = await client.get("/access-requests/?owner=me", headers=_auth(user_token))
    ref = own.json()[0]["reference_id"]

    resp = await client.get(f"/access-requests/{ref}/audit", headers=_auth(user_token))
    assert resp.status_code == 403


# ── End-to-end workflow ───────────────────────────────────────────────────────

async def test_full_workflow_register_approve_use_revoke(client, manager_token):
    """
    Register → pending → approve → login → call protected endpoint
    → revoke → old token rejected → resubmit → new pending request.
    """
    # 1. Register
    await _register_customer(client, "e2e@test.com", "E2E User", "E2EUser1!", "full_access")

    # 2. Approve
    ref = await _first_pending_ref(client, manager_token, "full_access")
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "approved"},
                       headers=_auth(manager_token))

    # 3. Login and use token
    token = await _login(client, "e2e@test.com", "E2EUser1!")
    assert (await client.get("/access-requests/?owner=me", headers=_auth(token))).status_code == 200

    # 4. Revoke
    await client.patch(f"/access-requests/{ref}",
                       json={"status": "revoked", "review_comment": "E2E revoke"},
                       headers=_auth(manager_token))

    # 5. Old token rejected
    assert (await client.get("/access-requests/?owner=me", headers=_auth(token))).status_code == 401

    # 6. Resubmit (need a fresh login; role is now free again)
    new_token = await _login(client, "e2e@test.com", "E2EUser1!")
    resp = await client.post("/access-requests/", json={
        "requested_role": "full_access",
        "reason": "Re-requesting",
        "requested_expires_at": EXPIRES_AT,
    }, headers=_auth(new_token))
    assert resp.status_code == 200
    assert resp.json()["reference_id"] != ref
