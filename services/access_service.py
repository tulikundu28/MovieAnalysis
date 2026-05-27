"""Business logic for access request lifecycle: submit, review, cancel, revoke, and audit."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional
from datetime import datetime
from repositories.access_repository import (
    create_access_request,
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
from utils.errors import (
    InvalidRoleError,
    DuplicatePendingRequestError,
    RequestNotFoundError,
    NotAuthorisedToViewError,
    NotAuthorisedToCancelError,
    NotAuthorisedToReviewError,
    NotAuthorisedToRevokeError,
    RequestNotCancellableError,
    RequestNotRevocableError,
    RequestAlreadyReviewedError,
    CommentRequiredError,
)

logger = logging.getLogger(__name__)

ROLE_APPROVER_MAP = {
    UserRole.FULL_ACCESS:    UserRole.MANAGER,
    UserRole.MOVIE_ADMIN:    UserRole.WORKFLOW_ADMIN,
    UserRole.MANAGER:        UserRole.WORKFLOW_ADMIN,
    UserRole.WORKFLOW_ADMIN: UserRole.WORKFLOW_ADMIN,
}

MOVIE_CUSTOMER_ROLES = {UserRole.FULL_ACCESS, UserRole.MOVIE_ADMIN}
WORKFLOW_ROLES       = {UserRole.MANAGER, UserRole.WORKFLOW_ADMIN}


async def submit_access_request(
    db: AsyncSession,
    requester_id: int,
    requested_role: str,
    reason: str,
    requested_expires_at: datetime,
) -> dict[str, Any]:
    """Submit a new role-upgrade request on behalf of a movie customer.

    Args:
        db: Active database session.
        requester_id: ID of the user submitting the request.
        requested_role: Role being requested; must be in MOVIE_CUSTOMER_ROLES.
        reason: Free-text justification for the request.
        requested_expires_at: Desired expiry datetime for the role grant.

    Returns:
        dict of the newly created access request row.

    Raises:
        InvalidRoleError: If requested_role is not a valid movie-customer role.
        DuplicatePendingRequestError: If the user already has a pending request.
    """
    if requested_role not in MOVIE_CUSTOMER_ROLES:
        logger.warning("Invalid role request by user_id=%d: %s", requester_id, requested_role)
        raise InvalidRoleError("Movie customers can only request full_access or movie_admin")

    existing = await get_pending_request_for_user(db, requester_id)
    if existing:
        logger.warning("Duplicate pending request from user_id=%d ref=%s", requester_id, existing.reference_id)
        raise DuplicatePendingRequestError(str(existing.reference_id))

    request = await create_access_request(db, requester_id, requested_role, reason, requested_expires_at)
    await insert_audit_log(db, request.id, requester_id, AuditAction.SUBMITTED, None)
    await db.commit()

    logger.info("Access request submitted: user_id=%d role=%s ref=%s", requester_id, requested_role, request.reference_id)
    return dict(request._mapping)


async def fetch_user_access_requests(db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    """Return all access requests submitted by the given user.

    Args:
        db: Active database session.
        user_id: ID of the user whose requests to retrieve.

    Returns:
        List of access request dicts ordered by creation date descending.
    """
    rows = await get_access_requests_by_requester(db, user_id)
    return [dict(row._mapping) for row in rows]




async def fetch_access_request(
    db: AsyncSession,
    reference_id: str,
    caller_id: Optional[int] = None,
    caller_role: Optional[str] = None,
) -> dict[str, Any]:
    """Fetch an access request, enforcing visibility rules based on the caller's identity.

    Args:
        db: Active database session.
        reference_id: UUID string identifying the access request.
        caller_id: ID of the authenticated caller, or None for unauthenticated access.
        caller_role: Role of the authenticated caller, or None for unauthenticated access.

    Returns:
        Full access request dict for the owner or a manager/admin.
        Status-only dict (reference_id, requested_role, status, review_comment)
        for unauthenticated callers.

    Raises:
        RequestNotFoundError: If no request matches the reference_id.
        NotAuthorisedToViewError: If the caller is authenticated but is neither
            the owner nor a manager/workflow_admin.
    """
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        logger.warning("Request not found: ref=%s caller_id=%s", reference_id, caller_id)
        raise RequestNotFoundError()

    if caller_id is None:
        return {
            "reference_id": str(request.reference_id),
            "requested_role": request.requested_role,
            "status": request.status,
            "review_comment": request.review_comment,
        }

    if caller_role not in (UserRole.MANAGER, UserRole.WORKFLOW_ADMIN) and request.requester_id != caller_id:
        logger.warning("Unauthorised view: ref=%s caller_id=%d", reference_id, caller_id)
        raise NotAuthorisedToViewError()

    return dict(request._mapping)


async def cancel_own_request(db: AsyncSession, reference_id: str, requester_id: int) -> dict[str, Any]:
    """Cancel the caller's own pending access request.

    Args:
        db: Active database session.
        reference_id: UUID string identifying the request to cancel.
        requester_id: ID of the user attempting the cancellation.

    Returns:
        dict of the updated access request row with status CANCELLED.

    Raises:
        RequestNotFoundError: If no request matches the reference_id.
        NotAuthorisedToCancelError: If the request belongs to a different user.
        RequestNotCancellableError: If the request is not in PENDING status.
    """
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        logger.warning("Cancel failed — request not found: ref=%s", reference_id)
        raise RequestNotFoundError()

    if request.requester_id != requester_id:
        logger.warning("Unauthorised cancel: ref=%s requester_id=%d caller_id=%d", reference_id, request.requester_id, requester_id)
        raise NotAuthorisedToCancelError()

    if request.status != RequestStatus.PENDING:
        logger.warning("Cancel failed — non-pending request: ref=%s status=%s", reference_id, request.status)
        raise RequestNotCancellableError()

    updated = await cancel_access_request(db, request.id, requester_id)
    await insert_audit_log(db, request.id, requester_id, AuditAction.CANCELLED, None)
    await db.commit()

    logger.info("Request cancelled: ref=%s user_id=%d", reference_id, requester_id)
    return dict(updated._mapping)


async def fetch_audit_log(db: AsyncSession, reference_id: str) -> list[dict[str, Any]]:
    """Return the full audit trail for an access request.

    Args:
        db: Active database session.
        reference_id: UUID string identifying the access request.

    Returns:
        List of audit log entry dicts ordered by creation date ascending,
        each including the actor's display name.

    Raises:
        RequestNotFoundError: If no request matches the reference_id.
    """
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        logger.warning("Audit log fetch — request not found: ref=%s", reference_id)
        raise RequestNotFoundError()
    rows = await get_audit_logs_for_request(db, request.id)
    return [dict(row._mapping) for row in rows]


async def revoke_access_request(
    db: AsyncSession,
    reference_id: str,
    revoker_id: int,
    revoker_role: str,
    review_comment: Optional[str],
) -> dict[str, Any]:
    """Revoke a previously approved access request and strip the user's role.

    Args:
        db: Active database session.
        reference_id: UUID string identifying the request to revoke.
        revoker_id: ID of the admin performing the revocation.
        revoker_role: Role of the admin; must match the required approver for the requested role.
        review_comment: Optional reason for revocation (written to the audit log).

    Returns:
        dict of the updated access request row with status REVOKED.

    Raises:
        RequestNotFoundError: If no request matches the reference_id.
        RequestNotRevocableError: If the request is not currently APPROVED.
        NotAuthorisedToRevokeError: If revoker_role does not have permission to revoke this role.
    """
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        logger.warning("Revoke failed — request not found: ref=%s", reference_id)
        raise RequestNotFoundError()

    if request.status != RequestStatus.APPROVED:
        logger.warning("Revoke failed — non-approved request: ref=%s status=%s", reference_id, request.status)
        raise RequestNotRevocableError()

    required_approver = ROLE_APPROVER_MAP.get(request.requested_role)
    if revoker_role != required_approver:
        logger.warning("Unauthorised revoke: ref=%s revoker_role=%s required=%s", reference_id, revoker_role, required_approver)
        raise NotAuthorisedToRevokeError()

    updated = await update_access_request(db, request.id, RequestStatus.REVOKED, revoker_id, review_comment)
    await update_user_role(db, request.requester_id, UserRole.FREE, None)
    await revoke_user_tokens(db, request.requester_id)
    await insert_audit_log(db, request.id, revoker_id, AuditAction.REVOKED, review_comment)
    await db.commit()

    logger.info("Request revoked: ref=%s revoker_id=%d requester_id=%d", reference_id, revoker_id, request.requester_id)
    return dict(updated._mapping)


async def fetch_access_requests(db: AsyncSession, caller_role: str, status: Optional[str] = None) -> list[dict[str, Any]]:
    """Return the queue of access requests visible to the caller's role.

    Args:
        db: Active database session.
        caller_role: Role of the caller; determines which requested_roles are visible
                     via ROLE_APPROVER_MAP.
        status: Optional status filter (e.g. 'pending', 'approved').

    Returns:
        List of access request dicts the caller is authorised to review.
    """
    requested_roles = [role for role, approver in ROLE_APPROVER_MAP.items() if approver == caller_role]
    rows = await get_access_requests(db, status, requested_roles)
    return [dict(row._mapping) for row in rows]


async def review_access_request(
    db: AsyncSession,
    reference_id: str,
    reviewer_id: int,
    reviewer_role: str,
    new_status: str,
    review_comment: Optional[str],
) -> dict[str, Any]:
    """Approve or deny a pending access request.

    On approval: upgrades the user's role, issues a new JWT, and persists the token.
    On denial: a review_comment is required.

    Args:
        db: Active database session.
        reference_id: UUID string identifying the request to review.
        reviewer_id: ID of the reviewer.
        reviewer_role: Role of the reviewer; must match the required approver for the requested role.
        new_status: Target status — 'approved' or 'denied'.
        review_comment: Required when denying; optional when approving.

    Returns:
        dict of the updated access request row. Includes 'api_token' key
        with the newly issued JWT when the request is approved.

    Raises:
        RequestNotFoundError: If no request matches the reference_id.
        RequestAlreadyReviewedError: If the request is not in PENDING status.
        NotAuthorisedToReviewError: If reviewer_role cannot review this role.
        CommentRequiredError: If new_status is 'denied' and no comment is provided.
    """
    request = await get_access_request_by_reference_id(db, reference_id)
    if not request:
        logger.warning("Review failed — request not found: ref=%s", reference_id)
        raise RequestNotFoundError()

    if request.status != RequestStatus.PENDING:
        logger.warning("Review failed — already reviewed: ref=%s status=%s", reference_id, request.status)
        raise RequestAlreadyReviewedError()

    required_approver = ROLE_APPROVER_MAP.get(request.requested_role)
    if reviewer_role != required_approver:
        logger.warning("Unauthorised review: ref=%s reviewer_role=%s required=%s", reference_id, reviewer_role, required_approver)
        raise NotAuthorisedToReviewError()

    if new_status == RequestStatus.DENIED and not review_comment:
        logger.warning("Review denied without comment: ref=%s reviewer_id=%d", reference_id, reviewer_id)
        raise CommentRequiredError()

    updated = await update_access_request(db, request.id, new_status, reviewer_id, review_comment)

    issued_token = None
    if new_status == RequestStatus.APPROVED:
        await update_user_role(db, request.requester_id, request.requested_role, request.requested_expires_at)
        requester = await get_user_by_id(db, request.requester_id)
        jwt_token = create_access_token(
            request.requester_id, request.requested_role,
            request.requested_expires_at,
            requester.name if requester else "",
        )
        await create_api_token(db, request.requester_id, request.id, request.requested_role, jwt_token, request.requested_expires_at)
        issued_token = jwt_token

    audit_action = AuditAction.APPROVED if new_status == RequestStatus.APPROVED else AuditAction.DENIED
    await insert_audit_log(db, request.id, reviewer_id, audit_action, review_comment)
    await db.commit()

    logger.info("Request reviewed: ref=%s status=%s reviewer_id=%d", reference_id, new_status, reviewer_id)
    result = dict(updated._mapping)
    if issued_token:
        result["api_token"] = issued_token
    return result
