from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from utils.helpers import CSVProcessorHelper
from repositories.movie_repository import get_movie_by_id, search_movies, insert_movies_batch, update_movie
from utils.constants import INSERTED_KEY, BATCH_SIZE, DEFAULT_PAGE_SIZE

async def fetch_movie_by_id(db: AsyncSession, movie_id: int):
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
        page_size: int = DEFAULT_PAGE_SIZE
):
    rows = await search_movies(db, title, release_year, genre, cursor, page_size)
    movies = [dict(row._mapping) for row in rows]
    next_cursor = movies[-1]["movie_id"] if len(movies) == page_size else None
    return {"data": movies, "next_cursor": next_cursor}


async def edit_movie(db: AsyncSession, movie_id: int, updates: dict):
    if not updates:
        movie = await get_movie_by_id(db, movie_id)
        return dict(movie._mapping) if movie else None
    row = await update_movie(db, movie_id, updates)
    return dict(row._mapping) if row else None


async def process_csv_upload(db: AsyncSession, file_bytes: bytes, batch_size: int=BATCH_SIZE):
    processor = CSVProcessorHelper()
    movies = processor.process(file_bytes)

    for i in range(0, len(movies), batch_size):
        await insert_movies_batch(db, movies[i:i + batch_size])

    return {INSERTED_KEY: len(movies)}