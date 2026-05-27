"""HTTP handler for workflow user registration."""
import logging
from typing import Any
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from models.auth import WorkflowRegisterRequest
from services.workflow_service import register_workflow_user as register_workflow_user_service

logger = logging.getLogger(__name__)


async def register_workflow_user(request: WorkflowRegisterRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Create a new workflow-approver account with a pending role request."""
    return await register_workflow_user_service(
        db,
        request.email,
        request.name,
        request.create_password.get_secret_value(),
        request.confirm_password.get_secret_value(),
        request.requested_role,
        request.reason,
    )
