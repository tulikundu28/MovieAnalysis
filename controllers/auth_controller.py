from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from models.auth import LoginRequest, RegisterRequest
from services.auth_service import login_user, register_user


async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    return await register_user(db, request.email, request.name, request.create_password.get_secret_value(), request.confirm_password.get_secret_value(), request.role)



async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await login_user(db, request.email, request.password.get_secret_value())
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return result
