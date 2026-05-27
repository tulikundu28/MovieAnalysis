"""FastAPI dependency functions for authentication and role-based access control."""
import logging
from typing import Optional
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from auth.jwt_handler import decode_access_token
from db.database import get_db
from repositories.access_repository import get_api_token
from utils.errors import TokenInvalidError, TokenRevokedError, InsufficientPermissionsError

logger = logging.getLogger(__name__)
bearer_scheme          = HTTPBearer()
optional_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate a Bearer JWT and confirm it is active in the database.

    Args:
        credentials: HTTP Bearer token extracted by FastAPI.
        db: Active database session used to check the token is not revoked.

    Returns:
        Decoded JWT payload dict (includes 'sub', 'role', 'name', 'exp').

    Raises:
        TokenInvalidError: If the JWT signature is invalid or the token has expired.
        TokenRevokedError: If the token is not found in the database or has been revoked.
    """
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        logger.warning("Token validation failed — invalid or expired JWT")
        raise TokenInvalidError()

    api_token = await get_api_token(db, token)
    if not api_token:
        logger.warning("Token lookup failed — revoked or unknown token")
        raise TokenRevokedError()

    return payload


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[dict]:
    """Optionally validate a Bearer JWT; return None when no token is provided.

    Args:
        credentials: Optional HTTP Bearer token; None when the header is absent.
        db: Active database session used to check the token is not revoked.

    Returns:
        Decoded JWT payload dict if a valid token was supplied, or None for
        unauthenticated requests.

    Raises:
        TokenInvalidError: If a token is provided but its signature is invalid or expired.
        TokenRevokedError: If a token is provided but has been revoked in the database.
    """
    if not credentials:
        return None
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise TokenInvalidError()
    api_token = await get_api_token(db, token)
    if not api_token:
        raise TokenRevokedError()
    return payload


def require_roles(*roles: str):
    """Return a FastAPI dependency that enforces one of the given roles on the request.

    Args:
        *roles: One or more role strings the caller must hold (OR logic).

    Returns:
        An async dependency function that resolves to the authenticated user's
        JWT payload dict, or raises InsufficientPermissionsError (403) if the
        user's role is not among the allowed roles.
    """
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            logger.warning(
                "Permission denied for user_id=%s role=%s — required one of %s",
                user.get("sub"), user.get("role"), roles,
            )
            raise InsufficientPermissionsError()
        return user
    return role_checker
