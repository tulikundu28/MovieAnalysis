import asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select, and_, or_
from db.tables import users_table, api_tokens_table
from db.database import AsyncSessionLocal
from utils.constants import LOGIN_SENTINEL_REQUEST_ID
from repositories.access_repository import get_latest_approved_request_per_user, insert_audit_log

DOWNGRADEABLE_ROLES = ('full_access', 'movie_admin')


async def downgrade_expired_or_revoked(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)

    # Users whose access-request token (request_id != sentinel) is still active (not revoked).
    # If none exist, the user's elevated access has been fully revoked.
    has_active_access_token = (
        select(api_tokens_table.c.user_id)
        .where(
            and_(
                api_tokens_table.c.request_id != LOGIN_SENTINEL_REQUEST_ID,
                api_tokens_table.c.revoked == False,
            )
        )
        .scalar_subquery()
    )

    result = await db.execute(
        update(users_table)
        .where(
            and_(
                users_table.c.role.in_(DOWNGRADEABLE_ROLES),
                users_table.c.expires_at.isnot(None),
                or_(
                    users_table.c.expires_at <= now,
                    users_table.c.id.not_in(has_active_access_token),
                ),
            )
        )
        .values(role="free", expires_at=None)
        .returning(users_table.c.id)
    )
    affected_ids = [row.id for row in result.fetchall()]

    if affected_ids:
        await db.execute(
            update(api_tokens_table)
            .where(
                and_(
                    api_tokens_table.c.user_id.in_(affected_ids),
                    api_tokens_table.c.revoked == False,
                )
            )
            .values(revoked=True)
        )
        request_map = await get_latest_approved_request_per_user(db, affected_ids)
        for user_id, request_id in request_map.items():
            await insert_audit_log(db, request_id, None, "expired", "Role expired or all access tokens revoked")

    await db.commit()
    return len(affected_ids)


async def role_expiry_loop(interval_seconds: int = 60):
    while True:
        await asyncio.sleep(interval_seconds)
        async with AsyncSessionLocal() as db:
            try:
                count = await downgrade_expired_or_revoked(db)
                if count:
                    print(f"[role-expiry] Downgraded {count} user(s) to free")
            except Exception as e:
                print(f"[role-expiry] Error: {e}")
