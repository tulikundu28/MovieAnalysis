import re
from typing import Literal
from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr, SecretStr, Field, field_validator


MOVIE_CUSTOMER_SIGNUP_ROLES = Literal['full_access', 'movie_admin']

_PW_MIN = 8


def _check_password_strength(v: SecretStr) -> SecretStr:
    pw = v.get_secret_value()
    if len(pw) < _PW_MIN:
        raise ValueError(f"Password must be at least {_PW_MIN} characters")
    if not re.search(r'[A-Z]', pw):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', pw):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r'\d', pw):
        raise ValueError("Password must contain at least one digit")
    return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    create_password: SecretStr
    confirm_password: SecretStr
    role: MOVIE_CUSTOMER_SIGNUP_ROLES = 'full_access'
    requested_expires_at: datetime

    @field_validator('name', mode='before')
    @classmethod
    def strip_name(cls, v):
        """Strip leading/trailing whitespace from the name field."""
        return v.strip() if isinstance(v, str) else v

    @field_validator('create_password', 'confirm_password')
    @classmethod
    def password_strength(cls, v: SecretStr) -> SecretStr:
        """Enforce minimum password strength: length, uppercase, lowercase, and digit."""
        return _check_password_strength(v)

    @field_validator('requested_expires_at')
    @classmethod
    def must_be_future(cls, v: datetime) -> datetime:
        """Reject expiry dates that are not in the future."""
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= datetime.now(timezone.utc):
            raise ValueError("Expiry date must be in the future")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str


class RegistrationResponse(BaseModel):
    reference_id: str
    message: str


class WorkflowRegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    create_password: SecretStr
    confirm_password: SecretStr
    requested_role: Literal['manager', 'workflow_admin']
    reason: str = Field(min_length=5, max_length=500)

    @field_validator('name', mode='before')
    @classmethod
    def strip_name(cls, v):
        """Strip leading/trailing whitespace from the name field."""
        return v.strip() if isinstance(v, str) else v

    @field_validator('create_password', 'confirm_password')
    @classmethod
    def password_strength(cls, v: SecretStr) -> SecretStr:
        """Enforce minimum password strength: length, uppercase, lowercase, and digit."""
        return _check_password_strength(v)

    @field_validator('reason', mode='before')
    @classmethod
    def strip_reason(cls, v):
        """Strip leading/trailing whitespace from the reason field."""
        return v.strip() if isinstance(v, str) else v
