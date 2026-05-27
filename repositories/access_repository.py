"""Database queries for access requests, API tokens, user roles, and audit logs."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Row, select, update, func
from typing import Any, Optional
from datetime import datetime, timezone
from db.tables import access_requests_table, audit_log_table, users_table, api_tokens_table
from utils.constants import RequestStatus

logger = logging.getLogger(__name__)


async def create_access_request(
    db: AsyncSession,
    requester_id: int,
    requested_role: str,
    reason: str,
    requested_expires_at: datetime,
) -> Row[Any]:
    """Insert a new access request row into the database.

    Args:
        db: Active database session.
        requester_id: ID of the user submitting the request.
        requested_role: Role string being requested.
        reason: Free-text justification provided by the requester.
        requested_expires_at: Desired expiry datetime for the role grant.

    Returns:
        SQLAlchemy Row for the newly created access request including
        the generated id and reference_id (UUID).
    """
    result = await db.execute(
        access_requests_table.insert()
        .values(
            requester_id=requester_id,
            requested_role=requested_role,
            reason=reason,
            requested_expires_at=requested_expires_at,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        .returning(*access_requests_table.c)
    )
    row = result.fetchone()
    logger.debug("Access request created: requester_id=%d role=%s ref=%s", requester_id, requested_role, row.reference_id)
    return row


async def get_access_request_by_reference_id(db: AsyncSession, reference_id: str) -> Row[Any] | None:
    """Fetch an access request by its public UUID reference.

    Args:
        db: Active database session.
        reference_id: UUID string used as the public-facing identifier.

    Returns:
        SQLAlchemy Row for the access request, or None if not found.
    """
    result = await db.execute(
        select(access_requests_table).where(access_requests_table.c.reference_id == reference_id)
    )
    return result.fetchone()


async def get_access_requests_by_requester(db: AsyncSession, requester_id: int) -> list[Row[Any]]:
    """Fetch all access requests submitted by a specific user.

    Args:
        db: Active database session.
        requester_id: ID of the user whose requests to retrieve.

    Returns:
        List of SQLAlchemy Rows ordered by created_at descending.
    """
    result = await db.execute(
        select(access_requests_table)
        .where(access_requests_table.c.requester_id == requester_id)
        .order_by(access_requests_table.c.created_at.desc())
    )
    return result.fetchall()


async def get_access_requests(
    db: AsyncSession,
    status: Optional[str] = None,
    requested_roles: Optional[list[str]] = None,
) -> list[Row[Any]]:
    """Fetch access requests with optional status and role filters.

    Args:
        db: Active database session.
        status: If provided, only rows with this status are returned.
        requested_roles: If provided, only rows whose requested_role is in
                         this list are returned.

    Returns:
        List of SQLAlchemy Rows ordered by created_at descending.
    """
    query = select(access_requests_table)
    if status is not None:
        query = query.where(access_requests_table.c.status == status)
    if requested_roles is not None:
        query = query.where(access_requests_table.c.requested_role.in_(requested_roles))
    result = await db.execute(query.order_by(access_requests_table.c.created_at.desc()))
    return result.fetchall()


async def update_access_request(
    db: AsyncSession,
    request_id: int,
    status: str,
    reviewed_by: int,
    review_comment: Optional[str],
) -> Row[Any]:
    """Update the status, reviewer, and comment on an access request.

    Args:
        db: Active database session.
        request_id: Internal integer primary key of the request.
        status: New status to set (e.g. 'approved', 'denied', 'revoked').
        reviewed_by: ID of the user performing the review.
        review_comment: Optional comment from the reviewer.

    Returns:
        SQLAlchemy Row with the updated access request data.
    """
    result = await db.execute(
        update(access_requests_table)
        .where(access_requests_table.c.id == request_id)
        .values(
            status=status,
            reviewed_by=reviewed_by,
            review_comment=review_comment,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(*access_requests_table.c)
    )
    row = result.fetchone()
    logger.debug("Access request updated: request_id=%d status=%s", request_id, status)
    return row


async def update_user_role(db: AsyncSession, user_id: int, role: str, expires_at: Optional[datetime]) -> None:
    """Set the role and expiry date on a user record.

    Args:
        db: Active database session.
        user_id: Primary key of the user to update.
        role: New role string to assign.
        expires_at: Datetime when the role should expire, or None for no expiry.
    """
    await db.execute(
        update(users_table)
        .where(users_table.c.id == user_id)
        .values(role=role, expires_at=expires_at)
    )
    logger.debug("User role updated: user_id=%d role=%s", user_id, role)


async def create_api_token(
    db: AsyncSession,
    user_id: int,
    request_id: int,
    tier: str,
    token: str,
    expires_at: datetime,
) -> Row[Any]:
    """Persist a new JWT as an API token record linked to a user and access request.

    Args:
        db: Active database session.
        user_id: ID of the token owner.
        request_id: ID of the access request that authorised this token.
                    Use LOGIN_SENTINEL_REQUEST_ID for login-issued tokens.
        tier: Role/tier string encoded in the token.
        token: Raw JWT string to store.
        expires_at: Expiry datetime for the token.

    Returns:
        SQLAlchemy Row for the newly created api_tokens row.
    """
    result = await db.execute(
        api_tokens_table.insert()
        .values(
            user_id=user_id,
            request_id=request_id,
            tier=tier,
            token=token,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )
        .returning(*api_tokens_table.c)
    )
    row = result.fetchone()
    logger.debug("API token created: user_id=%d tier=%s", user_id, tier)
    return row


async def get_api_token(db: AsyncSession, token: str) -> Row[Any] | None:
    """Look up an active (non-revoked) API token by its raw JWT string.

    Args:
        db: Active database session.
        token: Raw JWT string to look up.

    Returns:
        SQLAlchemy Row for the token record, or None if not found or revoked.
    """
    result = await db.execute(
        select(api_tokens_table).where(
            api_tokens_table.c.token == token,
            api_tokens_table.c.revoked == False,
        )
    )
    return result.fetchone()


async def get_pending_request_for_user(db: AsyncSession, requester_id: int) -> Row[Any] | None:
    """Fetch the most recent PENDING access request for a user.

    Args:
        db: Active database session.
        requester_id: ID of the user to check.

    Returns:
        SQLAlchemy Row for the pending request, or None if the user has no
        open pending requests.
    """
    result = await db.execute(
        select(access_requests_table)
        .where(
            access_requests_table.c.requester_id == requester_id,
            access_requests_table.c.status == RequestStatus.PENDING,
        )
        .order_by(access_requests_table.c.created_at.desc())
        .limit(1)
    )
    return result.fetchone()


async def cancel_access_request(db: AsyncSession, request_id: int, requester_id: int) -> Row[Any] | None:
    """Set a PENDING access request to CANCELLED.

    The WHERE clause guards against cancelling requests owned by other users
    or requests that are no longer pending.

    Args:
        db: Active database session.
        request_id: Internal integer primary key of the request.
        requester_id: ID of the user who must own the request.

    Returns:
        SQLAlchemy Row with the updated request data, or None if the conditions
        were not met (wrong owner or non-pending status).
    """
    result = await db.execute(
        update(access_requests_table)
        .where(
            access_requests_table.c.id == request_id,
            access_requests_table.c.requester_id == requester_id,
            access_requests_table.c.status == RequestStatus.PENDING,
        )
        .values(status=RequestStatus.CANCELLED, updated_at=datetime.now(timezone.utc))
        .returning(*access_requests_table.c)
    )
    return result.fetchone()


async def revoke_user_tokens(db: AsyncSession, user_id: int) -> None:
    """Mark all active (non-revoked) API tokens for a user as revoked.

    Args:
        db: Active database session.
        user_id: ID of the user whose tokens should be revoked.
    """
    await db.execute(
        update(api_tokens_table)
        .where(api_tokens_table.c.user_id == user_id, api_tokens_table.c.revoked == False)
        .values(revoked=True)
    )
    logger.debug("Tokens revoked for user_id=%d", user_id)


async def insert_audit_log(
    db: AsyncSession,
    request_id: int,
    actor_id: Optional[int],
    action: str,
    reason: Optional[str],
) -> None:
    """Append an immutable audit log entry for a lifecycle event on an access request.

    Args:
        db: Active database session.
        request_id: Internal integer primary key of the related access request.
        actor_id: ID of the user who triggered the action, or None for system actions.
        action: Action constant from AuditAction (e.g. SUBMITTED, APPROVED, EXPIRED).
        reason: Optional human-readable reason recorded alongside the action.
    """
    await db.execute(
        audit_log_table.insert().values(
            request_id=request_id,
            actor_id=actor_id,
            action=action,
            reason=reason,
            created_at=datetime.now(timezone.utc),
        )
    )
    logger.debug("Audit log entry: request_id=%d actor_id=%s action=%s", request_id, actor_id, action)


async def get_audit_logs_for_request(db: AsyncSession, request_id: int) -> list[Row[Any]]:
    """Fetch the full audit trail for an access request, including actor display names.

    Args:
        db: Active database session.
        request_id: Internal integer primary key of the access request.

    Returns:
        List of SQLAlchemy Rows (audit_log columns + actor_name) ordered by
        created_at ascending.
    """
    result = await db.execute(
        select(audit_log_table, users_table.c.name.label("actor_name"))
        .outerjoin(users_table, audit_log_table.c.actor_id == users_table.c.id)
        .where(audit_log_table.c.request_id == request_id)
        .order_by(audit_log_table.c.created_at.asc())
    )
    return result.fetchall()


async def get_latest_approved_request_per_user(db: AsyncSession, user_ids: list[int]) -> dict[int, int]:
    """Return the most recent approved access request ID for each of the given users.

    Args:
        db: Active database session.
        user_ids: List of user IDs to look up.

    Returns:
        Dict mapping user_id to the integer request_id of their latest approved request.
        Users with no approved requests are omitted from the result.
    """
    subq = (
        select(
            access_requests_table.c.requester_id,
            func.max(access_requests_table.c.id).label("request_id"),
        )
        .where(
            access_requests_table.c.requester_id.in_(user_ids),
            access_requests_table.c.status == RequestStatus.APPROVED,
        )
        .group_by(access_requests_table.c.requester_id)
        .subquery()
    )
    result = await db.execute(select(subq))
    return {row.requester_id: row.request_id for row in result.fetchall()}
