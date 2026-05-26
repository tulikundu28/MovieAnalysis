from fastapi import Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from db.database import get_db
from auth.dependencies import require_roles
from models.movie import MovieUpdate
from services.movie_service import fetch_movie_by_id, fetch_movies, process_csv_upload, edit_movie as edit_movie_service
from utils.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


async def search_movies(
    title: Optional[str] = Query(None),
    release_year: Optional[int] = Query(None),
    genre: Optional[str] = Query(None),
    cursor: Optional[int] = Query(None),
    page_size: int = Query(DEFAULT_PAGE_SIZE, le=MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db)
):
    return await fetch_movies(db, title, release_year, genre, cursor, page_size)


async def get_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    movie = await fetch_movie_by_id(db, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


async def upload_movies(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("movie_admin", "workflow_admin"))
):
    file_bytes = await file.read()
    return await process_csv_upload(db, file_bytes)


async def edit_movie(
    movie_id: int,
    body: MovieUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("movie_admin", "workflow_admin"))
):
    result = await edit_movie_service(db, movie_id, body.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=404, detail="Movie not found")
    return result
