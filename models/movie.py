from typing import Optional, List
from pydantic import BaseModel

class Movie(BaseModel):
    movie_id: int
    title: str
    release_year: Optional[int]
    genres: Optional[List[str]]

class MovieUpdate(BaseModel):
    title: Optional[str] = None
    release_year: Optional[int] = None
    genres: Optional[List[str]] = None

class MovieSearchResponse(BaseModel):
    data: List[Movie]
    next_cursor: Optional[int]