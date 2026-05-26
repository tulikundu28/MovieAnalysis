from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from db.database import get_db
from auth.dependencies import get_current_user, require_roles
from models.access import AccessRequestCreate, AccessRequestReview
from services.access_service import submit_access_request, fetch_access_requests, fetch_access_request, review_access_request, fetch_user_access_requests, revoke_access_request, fetch_audit_log, cancel_own_request
from fastapi import HTTPException, status as http_status
from utils.constants import UserRole, RequestStatus


async def create_access_request(
    body: AccessRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    return await submit_access_request(db, int(user["sub"]), body.requested_role, body.reason, body.requested_expires_at)


async def list_my_access_requests(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    return await fetch_user_access_requests(db, int(user["sub"]))


async def list_access_requests(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(UserRole.MANAGER, UserRole.WORKFLOW_ADMIN))
):
    return await fetch_access_requests(db, user["role"], status)


async def get_access_request(
    reference_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    return await fetch_access_request(db, reference_id, int(user["sub"]), user["role"])


async def review_request(
    reference_id: str,
    body: AccessRequestReview,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    if body.status == RequestStatus.CANCELLED:
        return await cancel_own_request(db, reference_id, int(user["sub"]))
    if user["role"] not in (UserRole.MANAGER, UserRole.WORKFLOW_ADMIN):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if body.status == RequestStatus.REVOKED:
        return await revoke_access_request(db, reference_id, int(user["sub"]), user["role"], body.review_comment)
    return await review_access_request(db, reference_id, int(user["sub"]), user["role"], body.status, body.review_comment)


async def get_audit_log_for_request(
    reference_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(UserRole.MANAGER, UserRole.WORKFLOW_ADMIN))
):
    return await fetch_audit_log(db, reference_id)


async def revoke_request(
    reference_id: str,
    body: AccessRequestReview,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(UserRole.MANAGER, UserRole.WORKFLOW_ADMIN))
):
    return await revoke_access_request(db, reference_id, int(user["sub"]), user["role"], body.review_comment)
