import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.tables import users_table

logger = logging.getLogger(__name__)


async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(users_table).where(users_table.c.email == email))
    return result.fetchone()


async def get_user_by_id(db: AsyncSession, user_id: int):
    result = await db.execute(select(users_table).where(users_table.c.id == user_id))
    return result.fetchone()


async def create_user(
    db: AsyncSession,
    email: str,
    name: str,
    hashed_password: str,
    user_type: str = "movie_customer",
    role: str = "free",
):
    result = await db.execute(
        users_table.insert()
        .values(email=email, name=name, password_hash=hashed_password, user_type=user_type, role=role)
        .returning(*users_table.c)
    )
    await db.commit()
    row = result.fetchone()
    logger.debug("User created: user_id=%d email=%s role=%s", row.id, email, role)
    return row
