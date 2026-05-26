from typing import Literal
from datetime import datetime
from pydantic import BaseModel, EmailStr, SecretStr

MOVIE_CUSTOMER_SIGNUP_ROLES = Literal['full_access', 'movie_admin']


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    create_password: SecretStr
    confirm_password: SecretStr
    role: MOVIE_CUSTOMER_SIGNUP_ROLES = 'full_access'
    requested_expires_at: datetime


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
    name: str
    create_password: SecretStr
    confirm_password: SecretStr
    requested_role: str  # 'manager' or 'admin'
    reason: str
