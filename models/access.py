from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AccessRequestCreate(BaseModel):
    requested_role: str
    reason: str
    requested_expires_at: datetime


class AccessRequestReview(BaseModel):
    status: str
    review_comment: Optional[str] = None


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
