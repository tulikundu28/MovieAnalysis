"""HTTP handlers for user registration and login."""
import logging
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from models.auth import LoginRequest, RegisterRequest, RegistrationResponse, TokenResponse
from services.auth_service import login_user, register_user
from utils.errors import InvalidCredentialsError

logger = logging.getLogger(__name__)


async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)) -> RegistrationResponse:
    """Create a new movie-customer account and submit an initial access request."""
    return await register_user(
        db,
        request.email,
        request.name,
        request.create_password.get_secret_value(),
        request.confirm_password.get_secret_value(),
        request.role,
        request.requested_expires_at,
    )


async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Authenticate a user and return a JWT access token."""
    result = await login_user(db, request.email, request.password.get_secret_value())
    if not result:
        raise InvalidCredentialsError()
    return result
