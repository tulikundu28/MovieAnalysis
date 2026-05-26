from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import Optional
from datetime import datetime
from repositories.access_repository import (
    create_access_request,
    get_access_request_by_id,
    get_access_request_by_reference_id,
    get_access_requests,
    get_access_requests_by_requester,
    update_access_request,
    update_user_role,
    create_api_token,
    revoke_user_tokens,
    insert_audit_log,
    get_audit_logs_for_request,
    get_pending_request_for_user,
    cancel_access_request,
)
from repositories.user_repository import get_user_by_id
from auth.jwt_handler import create_access_token
from utils.constants import UserRole, RequestStatus, AuditAction

ROLE_APPROVER_MAP = {
    UserRole.FULL_ACCESS:    UserRole.MANAGER,        # movie customer upgrade — manager approves
    UserRole.MOVIE_ADMIN:    UserRole.WORKFLOW_ADMIN, # movie customer admin — workflow_admin approves
    UserRole.MANAGER:        UserRole.WORKFLOW_ADMIN, # workflow approver registration — workflow_admin approves
    UserRole.WORKFLOW_ADMIN: UserRole.WORKFLOW_ADMIN, # workflow approver registration — workflow_admin approves
}

MOVIE_CUSTOMER_ROLES = {UserRole.FULL_ACCESS, UserRole.MOVIE_ADMIN}
WORKFLOW_ROLES       = {UserRole.MANAGER, UserRole.WORKFLOW_ADMIN}


async def submit_access_request(
    db: AsyncSession,
    requester_id: int,
    requested_role: str,
    reason: str,
    requested_expires_at: datetime
):
    if requested_role not in MOVIE_CUSTOMER_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Movie customers can only request full_access or movie_admin")

    existing = await get_pending_request_for_user(db, requester_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "You already have a pending request", "reference_id": str(existing.reference_id)}
        )

    request = await create_access_request(db, requester_id, requested_role, reason, requested_expires_at)
    await insert_audit_log(db, request.id, requester_id, AuditAction.SUBMITTED, None)
    await db.commit()
    return dict(request._mapping)


async def fetch_user_access_requests(db: AsyncSession, user_id: int):
    rows = await get_access_requests_by_requester(db, user_id)
    return [dict(row._mapping) for row in rows]


async def fetch_public_access_request(db: AsyncSession, reference_id: str):
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return {"reference_id": str(request.reference_id), "requested_role": request.requested_role,
            "status": request.status, "review_comment": request.review_comment}


async def fetch_access_request(
    db: AsyncSession,
    reference_id: str,
    caller_id: int,
    caller_role: str
):
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if caller_role not in (UserRole.MANAGER, UserRole.WORKFLOW_ADMIN) and request.requester_id != caller_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to view this request")
    return dict(request._mapping)


async def cancel_own_request(db: AsyncSession, reference_id: str, requester_id: int):
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if request.requester_id != requester_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to cancel this request")
    if request.status != RequestStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending requests can be cancelled")
    updated = await cancel_access_request(db, request.id, requester_id)
    await insert_audit_log(db, request.id, requester_id, AuditAction.CANCELLED, None)
    await db.commit()
    return dict(updated._mapping)


async def fetch_audit_log(db: AsyncSession, reference_id: str):
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    rows = await get_audit_logs_for_request(db, request.id)
    return [dict(row._mapping) for row in rows]


async def revoke_access_request(
    db: AsyncSession,
    reference_id: str,
    revoker_id: int,
    revoker_role: str,
    review_comment: Optional[str]
):
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if request.status != RequestStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved requests can be revoked")

    required_approver = ROLE_APPROVER_MAP.get(request.requested_role)
    if revoker_role != required_approver:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to revoke this request")

    updated = await update_access_request(db, request.id, RequestStatus.REVOKED, revoker_id, review_comment)
    await update_user_role(db, request.requester_id, UserRole.FREE, None)
    await revoke_user_tokens(db, request.requester_id)
    await insert_audit_log(db, request.id, revoker_id, AuditAction.REVOKED, review_comment)
    await db.commit()
    return dict(updated._mapping)


async def fetch_access_requests(
    db: AsyncSession,
    caller_role: str,
    status: Optional[str] = None
):
    # show only the requests this caller role is authorised to approve
    requested_roles = [role for role, approver in ROLE_APPROVER_MAP.items() if approver == caller_role]
    rows = await get_access_requests(db, status, requested_roles)
    return [dict(row._mapping) for row in rows]


async def review_access_request(
    db: AsyncSession,
    reference_id: str,
    reviewer_id: int,
    reviewer_role: str,
    new_status: str,
    review_comment: Optional[str]
):
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if request.status != RequestStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request already reviewed")

    required_approver = ROLE_APPROVER_MAP.get(request.requested_role)
    if reviewer_role != required_approver:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to review this request")

    if new_status == RequestStatus.DENIED and not review_comment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment required when denying")

    updated = await update_access_request(db, request.id, new_status, reviewer_id, review_comment)

    issued_token = None
    if new_status == RequestStatus.APPROVED:
        await update_user_role(db, request.requester_id, request.requested_role, request.requested_expires_at)
        requester = await get_user_by_id(db, request.requester_id)
        jwt_token = create_access_token(request.requester_id, request.requested_role, request.requested_expires_at, requester.name if requester else "")
        await create_api_token(db, request.requester_id, request.id, request.requested_role, jwt_token, request.requested_expires_at)
        issued_token = jwt_token

    await insert_audit_log(db, request.id, reviewer_id, AuditAction.APPROVED if new_status == RequestStatus.APPROVED else AuditAction.DENIED, review_comment)
    await db.commit()

    result = dict(updated._mapping)
    if issued_token:
        result["api_token"] = issued_token
    return result
