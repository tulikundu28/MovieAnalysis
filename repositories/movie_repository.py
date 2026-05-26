import logging
from typing import Any, Optional
from sqlalchemy import select, Row
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from db.tables import movies_table
from utils.constants import MovieColumns, DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)


async def get_movie_by_id(db: AsyncSession, movie_id: int) -> Row[Any] | None:
    result = await db.execute(
        select(movies_table).where(movies_table.c[MovieColumns.MOVIE_ID] == movie_id)
    )
    return result.fetchone()


async def search_movies(
    db: AsyncSession,
    title: Optional[str] = None,
    release_year: Optional[int] = None,
    genre: Optional[str] = None,
    cursor: Optional[int] = None,
    page_size: int = DEFAULT_PAGE_SIZE,
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
    stmt = pg_insert(movies_table).values(movies)
    stmt = stmt.on_conflict_do_update(
        index_elements=[MovieColumns.MOVIE_ID],
        set_={
            MovieColumns.TITLE: stmt.excluded.title,
            MovieColumns.RELEASE_YEAR: stmt.excluded.release_year,
            MovieColumns.GENRES: stmt.excluded.genres,
        },
    )
    await db.execute(stmt)
    await db.commit()
    logger.debug("Upserted batch of %d movies", len(movies))


async def update_movie(db: AsyncSession, movie_id: int, updates: dict):
    result = await db.execute(
        movies_table.update()
        .where(movies_table.c[MovieColumns.MOVIE_ID] == movie_id)
        .values(**updates)
        .returning(*movies_table.c)
    )
    await db.commit()
    return result.fetchone()
