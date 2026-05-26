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
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        logger.debug("JWT decode failed: %s", exc)
        return {}
