"""Business logic for movie retrieval, search, editing, and CSV bulk upload."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional
from utils.helpers import CSVProcessorHelper
from repositories.movie_repository import get_movie_by_id, search_movies, insert_movies_batch, update_movie
from utils.constants import INSERTED_KEY, BATCH_SIZE, DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)


async def fetch_movie_by_id(db: AsyncSession, movie_id: int) -> Optional[dict[str, Any]]:
    """Return a single movie as a plain dict.

    Args:
        db: Active database session.
        movie_id: Primary key of the movie to look up.

    Returns:
        dict with movie fields, or None if no matching row exists.
    """
    movie = await get_movie_by_id(db, movie_id)
    if not movie:
        return None
    return dict(movie._mapping)


async def fetch_movies(
    db: AsyncSession,
    title: Optional[str] = None,
    release_year: Optional[int] = None,
    genre: Optional[str] = None,
    cursor: Optional[int] = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Return a cursor-paginated list of movies with optional filters.

    Args:
        db: Active database session.
        title: Case-insensitive substring match on movie title.
        release_year: Exact year filter.
        genre: Genre string to match (title-cased, array contains).
        cursor: Exclusive lower bound on movie_id for keyset pagination.
        page_size: Maximum number of rows to return.

    Returns:
        dict with keys 'data' (list of movie dicts) and 'next_cursor'
        (int for the next page, or None if this is the last page).
    """
    rows = await search_movies(db, title, release_year, genre, cursor, page_size)
    movies = [dict(row._mapping) for row in rows]
    next_cursor = movies[-1]["movie_id"] if len(movies) == page_size else None
    return {"data": movies, "next_cursor": next_cursor}


async def edit_movie(db: AsyncSession, movie_id: int, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Apply a partial update to a movie and return the result.

    Args:
        db: Active database session.
        movie_id: Primary key of the movie to update.
        updates: Dict of field names to new values. Empty dict skips the
                 write and returns the current row unchanged.

    Returns:
        dict with updated movie fields, or None if the movie does not exist.
    """
    if not updates:
        movie = await get_movie_by_id(db, movie_id)
        return dict(movie._mapping) if movie else None
    row = await update_movie(db, movie_id, updates)
    if row:
        logger.info("Movie updated: movie_id=%d fields=%s", movie_id, list(updates.keys()))
    return dict(row._mapping) if row else None


async def process_csv_upload(db: AsyncSession, file_bytes: bytes, batch_size: int = BATCH_SIZE) -> dict[str, int]:
    """Parse a CSV file and bulk-upsert its movies into the database.

    Args:
        db: Active database session.
        file_bytes: Raw bytes of the uploaded CSV file.
        batch_size: Number of rows to upsert per database statement.

    Returns:
        dict with key 'inserted' containing the total number of rows processed.
    """
    processor = CSVProcessorHelper()
    movies = processor.process(file_bytes)

    for i in range(0, len(movies), batch_size):
        await insert_movies_batch(db, movies[i:i + batch_size])

    logger.info("CSV upload complete: %d movies inserted/updated", len(movies))
    return {INSERTED_KEY: len(movies)}
