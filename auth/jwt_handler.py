"""JWT creation and decoding using the HS256 algorithm."""
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from dotenv import load_dotenv
from utils.constants import JWT_ALGORITHM, JWT_EXPIRY_MINUTES

load_dotenv()

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    sys.exit("FATAL: required environment variable 'JWT_SECRET' is not set")


def create_access_token(user_id: int, role: str, expires_at: datetime | None, name: str = "") -> str:
    """Sign and return a new JWT access token.

    Args:
        user_id: ID of the user (encoded in the 'sub' claim as a string).
        role: Role string to embed in the 'role' claim.
        expires_at: Role expiry datetime written to the 'expires_at' claim
                    (not the same as the JWT 'exp' claim); None if the role
                    has no expiry.
        name: Display name of the user for the 'name' claim.

    Returns:
        Signed JWT string using the HS256 algorithm.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRY_MINUTES)
    payload = {
        "sub": str(user_id),
        "name": name,
        "role": role,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "exp": expire,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.debug("JWT created for user_id=%d role=%s", user_id, role)
    return token


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT, returning its payload.

    Args:
        token: Raw JWT string to decode.

    Returns:
        Decoded payload dict on success, or an empty dict if the token is
        invalid, expired, or has a bad signature.
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        logger.debug("JWT decode failed: %s", exc)
        return {}
