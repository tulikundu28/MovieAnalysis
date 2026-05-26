import os
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from dotenv import load_dotenv
from utils.constants import JWT_ALGORITHM, JWT_EXPIRY_MINUTES

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")


def create_access_token(user_id: int, role: str, expires_at: datetime | None, name: str = "") -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRY_MINUTES)
    payload = {
        "sub": str(user_id),
        "name": name,
        "role": role,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return {}
