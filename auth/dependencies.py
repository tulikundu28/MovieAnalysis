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
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            logger.warning(
                "Permission denied for user_id=%s role=%s — required one of %s",
                user.get("sub"), user.get("role"), roles,
            )
            raise InsufficientPermissionsError()
        return user
    return role_checker
