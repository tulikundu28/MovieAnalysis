import logging
from sqlalchemy.ext.asyncio import AsyncSession
from repositories.user_repository import get_user_by_email, create_user
from repositories.access_repository import create_access_request, insert_audit_log
from services.auth_service import hash_password
from services.access_service import WORKFLOW_ROLES
from utils.constants import UserType, AuditAction, WORKFLOW_EXPIRY_DATE
from utils.errors import InvalidRoleError, PasswordMismatchError, EmailAlreadyRegisteredError

logger = logging.getLogger(__name__)


async def register_workflow_user(
    db: AsyncSession,
    email: str,
    name: str,
    password: str,
    confirm_password: str,
    requested_role: str,
    reason: str,
):
    if requested_role not in WORKFLOW_ROLES:
        logger.warning("Invalid workflow role requested: %s email=%s", requested_role, email)
        raise InvalidRoleError("Workflow role must be 'manager' or 'workflow_admin'")

    if password != confirm_password:
        logger.warning("Workflow registration failed — password mismatch: email=%s", email)
        raise PasswordMismatchError()

    if await get_user_by_email(db, email):
        logger.warning("Workflow registration failed — email already registered: %s", email)
        raise EmailAlreadyRegisteredError()

    user = await create_user(db, email, name, hash_password(password), user_type=UserType.WORKFLOW_APPROVER)
    request = await create_access_request(db, user.id, requested_role, reason, WORKFLOW_EXPIRY_DATE)
    await insert_audit_log(db, request.id, user.id, AuditAction.SUBMITTED, None)
    await db.commit()

    logger.info("Workflow user registered: user_id=%d email=%s requested_role=%s", user.id, email, requested_role)
    return {
        "request_id": request.id,
        "message": f"Account created. Your {requested_role} request is pending admin approval.",
    }
