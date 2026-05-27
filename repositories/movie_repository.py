"""Database queries for the movies table: lookup, search, upsert batch, and update."""
import logging
from typing import Any, Optional
from sqlalchemy import select, Row
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from db.tables import movies_table
from utils.constants import MovieColumns, DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)


async def get_movie_by_id(db: AsyncSession, movie_id: int) -> Row[Any] | None:
    """Fetch a single movie row by primary key.

    Args:
        db: Active database session.
        movie_id: Primary key of the movie.

    Returns:
        Row for the movie, or None if not found.
    """
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
) -> list[Row[Any]]:
    """Query the movies table with optional filters and cursor-based pagination.

    Args:
        db: Active database session.
        title: ILIKE pattern substring to match against the title column.
        release_year: Exact year to filter on.
        genre: Single genre string (array-contains match, title-cased).
        cursor: If set, only rows with movie_id greater than this value are returned.
        page_size: Maximum number of rows to return.

    Returns:
        List of Row objects ordered by movie_id ascending.
    """
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


async def insert_movies_batch(db: AsyncSession, movies: list[dict[str, Any]]) -> None:
    """Upsert a batch of movie rows using PostgreSQL ON CONFLICT DO UPDATE.

    Conflicts on movie_id are resolved by overwriting title, release_year,
    and genres with the incoming values.

    Args:
        db: Active database session (committed inside this function).
        movies: List of dicts, each containing movie_id, title, release_year,
                and genres fields.
    """
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


async def update_movie(db: AsyncSession, movie_id: int, updates: dict[str, Any]) -> Row[Any] | None:
    """Apply arbitrary field updates to a movie row and return the result.

    Args:
        db: Active database session (committed inside this function).
        movie_id: Primary key of the movie to update.
        updates: Dict mapping column names to new values.

    Returns:
        Row with the updated movie data, or None if the movie_id
        did not match any row.
    """
    result = await db.execute(
        movies_table.update()
        .where(movies_table.c[MovieColumns.MOVIE_ID] == movie_id)
        .values(**updates)
        .returning(*movies_table.c)
    )
    await db.commit()
    return result.fetchone()
