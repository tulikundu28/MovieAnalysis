from typing import Optional, List
from pydantic import BaseModel

class Movie(BaseModel):
    movie_id: int
    title: str
    release_year: Optional[int]
    genres: Optional[List[str]]

class MovieSearchResponse(BaseModel):
    data: List[Movie]
    next_cursor: Optional[int]