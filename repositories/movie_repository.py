from typing import Any

from sqlalchemy import select, Row
from sqlalchemy.ext.asyncio import AsyncSession
from db.tables import movies_table
from utils.constants import MovieColumns, DEFAULT_PAGE_SIZE
from typing import Optional


async def get_movie_by_id(db: AsyncSession, movie_id: int) -> Row[Any] | None:
    query = select(movies_table).where(
        movies_table.c[MovieColumns.MOVIE_ID] == movie_id
    )
    result = await db.execute(query)
    return result.fetchone()


async def search_movies(
        db: AsyncSession,
        title: Optional[str] = None,
        release_year: Optional[int] = None,
        genre: Optional[str] = None,
        cursor: Optional[int] = None,
        page_size: int = DEFAULT_PAGE_SIZE
):
    query = select(movies_table)

    if title is not None:
        query = query.where(movies_table.c[MovieColumns.TITLE].ilike(f"%{title}%"))

    if release_year is not None:
        query = query.where(movies_table.c[MovieColumns.RELEASE_YEAR] == release_year)

    if genre is not None and genre.strip():
        query = query.where(movies_table.c[MovieColumns.GENRES].contains([genre.strip().title()]))

    if cursor is not None:
        query = query.where(movies_table.c[MovieColumns.MOVIE_ID] > cursor)

    query = query.order_by(movies_table.c[MovieColumns.MOVIE_ID]).limit(page_size)

    result = await db.execute(query)
    return result.fetchall()

async def insert_movies_batch(db: AsyncSession, movies: list[dict]):
    await db.execute(movies_table.insert(), movies)
    await db.commit()

async def update_movie(db: AsyncSession, movie_id: int, updates: dict):
    query = (
        movies_table.update()
        .where(movies_table.c[MovieColumns.MOVIE_ID] == movie_id)
        .values(**updates)
        .returning(*movies_table.c)
    )
    result = await db.execute(query)
    await db.commit()
    return result.fetchone()