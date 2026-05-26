from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.tables import users_table


async def get_user_by_email(db: AsyncSession, email: str):
    query = select(users_table).where(users_table.c.email == email)
    result = await db.execute(query)
    return result.fetchone()


async def get_user_by_id(db: AsyncSession, user_id: int):
    result = await db.execute(select(users_table).where(users_table.c.id == user_id))
    return result.fetchone()


async def create_user(db: AsyncSession, email: str, name: str, hashed_password: str, user_type: str = 'movie_customer', role: str = 'free'):
    query = users_table.insert().values(
        email=email,
        name=name,
        password_hash=hashed_password,
        user_type=user_type,
        role=role,
    ).returning(*users_table.c)
    result = await db.execute(query)
    await db.commit()
    return result.fetchone()
