"""Database queries for the users table: lookup by email/id and create."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Row, select
from typing import Any
from db.tables import users_table

logger = logging.getLogger(__name__)


async def get_user_by_email(db: AsyncSession, email: str) -> Row[Any] | None:
    """Look up a user by their email address.

    Args:
        db: Active database session.
        email: Email address to search for.

    Returns:
        Row for the user, or None if no match exists.
    """
    result = await db.execute(select(users_table).where(users_table.c.email == email))
    return result.fetchone()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Row[Any] | None:
    """Look up a user by their primary key.

    Args:
        db: Active database session.
        user_id: Primary key of the user.

    Returns:
        Row for the user, or None if not found.
    """
    result = await db.execute(select(users_table).where(users_table.c.id == user_id))
    return result.fetchone()


async def create_user(
    db: AsyncSession,
    email: str,
    name: str,
    hashed_password: str,
    user_type: str = "movie_customer",
    role: str = "free",
) -> Row[Any]:
    """Insert a new user row into the database and return it.

    Args:
        db: Active database session (committed inside this function).
        email: Unique email address for the new user.
        name: Display name.
        hashed_password: Pre-hashed password string (bcrypt).
        user_type: User type constant — 'movie_customer' or 'workflow_approver'.
        role: Initial role for the user, defaults to 'free'.

    Returns:
        Row for the newly created user including the generated id.
    """
    result = await db.execute(
        users_table.insert()
        .values(email=email, name=name, password_hash=hashed_password, user_type=user_type, role=role)
        .returning(*users_table.c)
    )
    await db.commit()
    row = result.fetchone()
    logger.debug("User created: user_id=%d email=%s role=%s", row.id, email, role)
    return row
