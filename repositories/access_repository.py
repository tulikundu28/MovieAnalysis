from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional
from datetime import datetime, timezone
from db.tables import access_requests_table, audit_log_table, users_table, api_tokens_table
from utils.constants import RequestStatus


async def create_access_request(
    db: AsyncSession,
    requester_id: int,
    requested_role: str,
    reason: str,
    requested_expires_at: datetime
):
    query = access_requests_table.insert().values(
        requester_id=requester_id,
        requested_role=requested_role,
        reason=reason,
        requested_expires_at=requested_expires_at,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    ).returning(*access_requests_table.c)
    result = await db.execute(query)
    return result.fetchone()


async def get_access_request_by_reference_id(db: AsyncSession, reference_id: str):
    query = select(access_requests_table).where(
        access_requests_table.c.reference_id == reference_id
    )
    result = await db.execute(query)
    return result.fetchone()


async def get_access_request_by_id(db: AsyncSession, request_id: int):
    query = select(access_requests_table).where(
        access_requests_table.c.id == request_id
    )
    result = await db.execute(query)
    return result.fetchone()


async def get_access_requests_by_requester(db: AsyncSession, requester_id: int):
    query = (
        select(access_requests_table)
        .where(access_requests_table.c.requester_id == requester_id)
        .order_by(access_requests_table.c.created_at.desc())
    )
    result = await db.execute(query)
    return result.fetchall()


async def get_access_requests(
    db: AsyncSession,
    status: Optional[str] = None,
    requested_roles: Optional[list] = None
):
    query = select(access_requests_table)

    if status is not None:
        query = query.where(access_requests_table.c.status == status)

    if requested_roles is not None:
        query = query.where(access_requests_table.c.requested_role.in_(requested_roles))

    query = query.order_by(access_requests_table.c.created_at.desc())
    result = await db.execute(query)
    return result.fetchall()


async def update_access_request(
    db: AsyncSession,
    request_id: int,
    status: str,
    reviewed_by: int,
    review_comment: Optional[str]
):
    query = update(access_requests_table).where(
        access_requests_table.c.id == request_id
    ).values(
        status=status,
        reviewed_by=reviewed_by,
        review_comment=review_comment,
        updated_at=datetime.now(timezone.utc)
    ).returning(*access_requests_table.c)
    result = await db.execute(query)
    return result.fetchone()


async def update_user_role(
    db: AsyncSession,
    user_id: int,
    role: str,
    expires_at: datetime
):
    query = update(users_table).where(
        users_table.c.id == user_id
    ).values(
        role=role,
        expires_at=expires_at
    )
    await db.execute(query)


async def create_api_token(
    db: AsyncSession,
    user_id: int,
    request_id: int,
    tier: str,
    token: str,
    expires_at: datetime
):
    query = api_tokens_table.insert().values(
        user_id=user_id,
        request_id=request_id,
        tier=tier,
        token=token,
        expires_at=expires_at,
        created_at=datetime.now(timezone.utc)
    ).returning(*api_tokens_table.c)
    result = await db.execute(query)
    return result.fetchone()


async def get_api_token(db: AsyncSession, token: str):
    query = select(api_tokens_table).where(
        api_tokens_table.c.token == token,
        api_tokens_table.c.revoked == False
    )
    result = await db.execute(query)
    return result.fetchone()


async def get_pending_request_for_user(db: AsyncSession, requester_id: int):
    result = await db.execute(
        select(access_requests_table)
        .where(
            access_requests_table.c.requester_id == requester_id,
            access_requests_table.c.status == RequestStatus.PENDING
        )
        .order_by(access_requests_table.c.created_at.desc())
        .limit(1)
    )
    return result.fetchone()


async def cancel_access_request(db: AsyncSession, request_id: int, requester_id: int):
    result = await db.execute(
        update(access_requests_table)
        .where(
            access_requests_table.c.id == request_id,
            access_requests_table.c.requester_id == requester_id,
            access_requests_table.c.status == RequestStatus.PENDING
        )
        .values(status=RequestStatus.CANCELLED, updated_at=datetime.now(timezone.utc))
        .returning(*access_requests_table.c)
    )
    return result.fetchone()


async def revoke_user_tokens(db: AsyncSession, user_id: int):
    await db.execute(
        update(api_tokens_table)
        .where(api_tokens_table.c.user_id == user_id, api_tokens_table.c.revoked == False)
        .values(revoked=True)
    )


async def insert_audit_log(
    db: AsyncSession,
    request_id: int,
    actor_id: Optional[int],
    action: str,
    reason: Optional[str]
):
    query = audit_log_table.insert().values(
        request_id=request_id,
        actor_id=actor_id,
        action=action,
        reason=reason,
        created_at=datetime.now(timezone.utc)
    )
    await db.execute(query)


async def get_audit_logs_for_request(db: AsyncSession, request_id: int):
    result = await db.execute(
        select(
            audit_log_table,
            users_table.c.name.label("actor_name")
        )
        .outerjoin(users_table, audit_log_table.c.actor_id == users_table.c.id)
        .where(audit_log_table.c.request_id == request_id)
        .order_by(audit_log_table.c.created_at.asc())
    )
    return result.fetchall()


async def get_latest_approved_request_per_user(db: AsyncSession, user_ids: list[int]):
    """Returns {user_id: request_id} for the most recent approved request per user."""
    from sqlalchemy import func
    subq = (
        select(
            access_requests_table.c.requester_id,
            func.max(access_requests_table.c.id).label("request_id")
        )
        .where(
            access_requests_table.c.requester_id.in_(user_ids),
            access_requests_table.c.status == RequestStatus.APPROVED
        )
        .group_by(access_requests_table.c.requester_id)
        .subquery()
    )
    result = await db.execute(select(subq))
    return {row.requester_id: row.request_id for row in result.fetchall()}
