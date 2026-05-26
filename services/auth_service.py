from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from passlib.context import CryptContext
from auth.jwt_handler import create_access_token
from repositories.user_repository import get_user_by_email, create_user
from repositories.access_repository import create_api_token, create_access_request, insert_audit_log
from utils.constants import JWT_EXPIRY_MINUTES, LOGIN_SENTINEL_REQUEST_ID, UserType, UserRole, AuditAction, TOKEN_TYPE, REGISTRATION_REASON

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


async def register_user(db: AsyncSession, email: str, name: str, create_password: str, confirm_password: str, role: str, requested_expires_at: datetime):
    if create_password != confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    existing = await get_user_by_email(db, email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    hashed = hash_password(create_password)
    user = await create_user(db, email, name, hashed, user_type=UserType.MOVIE_CUSTOMER, role=UserRole.FREE)
    req = await create_access_request(db, user.id, role, REGISTRATION_REASON, requested_expires_at)
    await insert_audit_log(db, req.id, user.id, AuditAction.SUBMITTED, None)
    await db.commit()
    return {"reference_id": str(req.reference_id), "message": f"Request submitted. Awaiting {role} approval."}


async def login_user(db: AsyncSession, email: str, password: str):
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return None
    token = create_access_token(user.id, user.role, user.expires_at, user.name)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRY_MINUTES)
    await create_api_token(db, user.id, LOGIN_SENTINEL_REQUEST_ID, user.role, token, expires_at)
    await db.commit()
    return {"access_token": token, "token_type": TOKEN_TYPE}
