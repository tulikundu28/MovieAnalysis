"""HTTP handlers for movie-related endpoints (search, get, upload, edit)."""
import logging
from fastapi import Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional
from db.database import get_db
from auth.dependencies import require_roles
from models.movie import MovieUpdate
from services.movie_service import fetch_movie_by_id, fetch_movies, process_csv_upload, edit_movie as edit_movie_service
from utils.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, UserRole
from utils.errors import MovieNotFoundError

logger = logging.getLogger(__name__)


async def search_movies(
    title: Optional[str] = Query(None),
    release_year: Optional[int] = Query(None),
    genre: Optional[str] = Query(None),
    cursor: Optional[int] = Query(None),
    page_size: int = Query(DEFAULT_PAGE_SIZE, le=MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return a paginated list of movies, optionally filtered by title, year, and genre."""
    return await fetch_movies(db, title, release_year, genre, cursor, page_size)


async def get_movie(movie_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return a single movie by ID, or raise 404 if not found."""
    movie = await fetch_movie_by_id(db, movie_id)
    if not movie:
        logger.warning("Movie not found: movie_id=%d", movie_id)
        raise MovieNotFoundError()
    return movie


async def upload_movies(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(require_roles(UserRole.MOVIE_ADMIN, UserRole.WORKFLOW_ADMIN)),
) -> dict[str, int]:
    """Accept a CSV file and bulk-upsert its movies. Requires MOVIE_ADMIN or WORKFLOW_ADMIN role."""
    file_bytes = await file.read()
    return await process_csv_upload(db, file_bytes)


async def edit_movie(
    movie_id: int,
    body: MovieUpdate,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(require_roles(UserRole.MOVIE_ADMIN, UserRole.WORKFLOW_ADMIN)),
) -> dict[str, Any]:
    """Partially update a movie's fields. Requires MOVIE_ADMIN or WORKFLOW_ADMIN role."""
    result = await edit_movie_service(db, movie_id, body.model_dump(exclude_none=True))
    if not result:
        logger.warning("Edit failed — movie not found: movie_id=%d", movie_id)
        raise MovieNotFoundError()
    return result
