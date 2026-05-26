import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from auth.jwt_handler import create_access_token
from repositories.user_repository import get_user_by_email, create_user
from repositories.access_repository import create_api_token, create_access_request, insert_audit_log
from utils.constants import JWT_EXPIRY_MINUTES, LOGIN_SENTINEL_REQUEST_ID, UserType, UserRole, AuditAction, TOKEN_TYPE, REGISTRATION_REASON
from utils.errors import PasswordMismatchError, EmailAlreadyRegisteredError
from models.auth import RegistrationResponse, TokenResponse

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


async def register_user(
    db: AsyncSession,
    email: str,
    name: str,
    create_password: str,
    confirm_password: str,
    role: str,
    requested_expires_at: datetime,
):
    if create_password != confirm_password:
        logger.warning("Registration failed — password mismatch: email=%s", email)
        raise PasswordMismatchError()

    if await get_user_by_email(db, email):
        logger.warning("Registration failed — email already registered: %s", email)
        raise EmailAlreadyRegisteredError()

    hashed = hash_password(create_password)
    user = await create_user(db, email, name, hashed, user_type=UserType.MOVIE_CUSTOMER, role=UserRole.FREE)
    req = await create_access_request(db, user.id, role, REGISTRATION_REASON, requested_expires_at)
    await insert_audit_log(db, req.id, user.id, AuditAction.SUBMITTED, None)
    await db.commit()

    logger.info("Movie customer registered: user_id=%d email=%s requested_role=%s", user.id, email, role)
    return RegistrationResponse(
        reference_id=str(req.reference_id),
        message=f"Request submitted. Awaiting {role} approval.",
    )


async def login_user(db: AsyncSession, email: str, password: str):
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        logger.warning("Login failed for email=%s", email)
        return None

    token = create_access_token(user.id, user.role, user.expires_at, user.name)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRY_MINUTES)
    await create_api_token(db, user.id, LOGIN_SENTINEL_REQUEST_ID, user.role, token, expires_at)
    await db.commit()

    logger.info("User logged in: user_id=%d role=%s", user.id, user.role)
    return TokenResponse(access_token=token, token_type=TOKEN_TYPE)
