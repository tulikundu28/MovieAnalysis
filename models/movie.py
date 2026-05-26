from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class Movie(BaseModel):
    movie_id: int
    title: str
    release_year: Optional[int]
    genres: Optional[List[str]]


class MovieUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    release_year: Optional[int] = Field(None, ge=1888, le=2200)
    genres: Optional[List[str]] = None

    @field_validator('title', mode='before')
    @classmethod
    def strip_title(cls, v):
        if isinstance(v, str):
            stripped = v.strip()
            return stripped if stripped else None
        return v

    @field_validator('genres')
    @classmethod
    def genres_not_empty(cls, v):
        if v is not None:
            if len(v) == 0:
                raise ValueError("Genres list cannot be empty — omit the field to leave unchanged")
            for genre in v:
                if not isinstance(genre, str) or not genre.strip():
                    raise ValueError("Each genre must be a non-empty string")
        return v


class MovieSearchResponse(BaseModel):
    data: List[Movie]
    next_cursor: Optional[int]
