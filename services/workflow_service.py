from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from repositories.user_repository import get_user_by_email, create_user
from repositories.access_repository import create_access_request, insert_audit_log
from services.auth_service import hash_password
from services.access_service import WORKFLOW_ROLES
from utils.constants import UserType, AuditAction, WORKFLOW_EXPIRY_DATE


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Workflow role must be 'manager' or 'workflow_admin'")
    if password != confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    if await get_user_by_email(db, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = await create_user(db, email, name, hash_password(password), user_type=UserType.WORKFLOW_APPROVER)
    request = await create_access_request(db, user.id, requested_role, reason, WORKFLOW_EXPIRY_DATE)
    await insert_audit_log(db, request.id, user.id, AuditAction.SUBMITTED, None)
    await db.commit()
    return {
        "request_id": request.id,
        "message": f"Account created. Your {requested_role} request is pending admin approval."
    }
