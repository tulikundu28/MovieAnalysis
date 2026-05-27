from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime, timezone


class AccessRequestCreate(BaseModel):
    requested_role: Literal['full_access', 'movie_admin']
    reason: str = Field(min_length=5, max_length=500)
    requested_expires_at: datetime

    @field_validator('reason', mode='before')
    @classmethod
    def strip_reason(cls, v):
        """Strip leading/trailing whitespace from the reason field."""
        return v.strip() if isinstance(v, str) else v

    @field_validator('requested_expires_at')
    @classmethod
    def must_be_future(cls, v: datetime) -> datetime:
        """Reject expiry dates that are not in the future."""
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= datetime.now(timezone.utc):
            raise ValueError("Expiry date must be in the future")
        return v


class AccessRequestReview(BaseModel):
    status: Literal['approved', 'denied', 'revoked', 'cancelled']
    review_comment: Optional[str] = Field(None, max_length=1000)

    @field_validator('review_comment', mode='before')
    @classmethod
    def strip_comment(cls, v):
        """Strip whitespace from the review comment; return None if the result is empty."""
        if isinstance(v, str):
            stripped = v.strip()
            return stripped if stripped else None
        return v


class AccessRequestResponse(BaseModel):
    reference_id: str
    requester_id: int
    requested_role: str
    reason: str
    status: str
    reviewed_by: Optional[int]
    review_comment: Optional[str]
    requested_expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ReviewResponse(AccessRequestResponse):
    api_token: Optional[str] = None


class AccessRequestStatusResponse(BaseModel):
    reference_id: str
    requested_role: str
    status: str
    review_comment: Optional[str] = None
