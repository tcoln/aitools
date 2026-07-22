# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.user import UserCreate, UserLogin, Token, UserResponse
from models.user import User
from services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()


# 从请求头获取JWT令牌并返回当前用户，验证失败抛出401
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = AuthService.decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="无效的认证令牌")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的认证令牌")
    user = await AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="用户已被禁用")
    return user


# 依赖注入：要求当前用户为管理员，否则抛出403
async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


# 用户注册：创建新用户，第一个用户自动设为管理员
@router.post("/register", response_model=Token)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await AuthService.get_user_by_username(db, data.username)
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    result = await db.execute(select(func.count(User.id)))
    user_count = result.scalar()

    user = User(
        username=data.username,
        password_hash=AuthService.hash_password(data.password),
        display_name=data.display_name or data.username,
        email=data.email,
        is_admin=(user_count == 0),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = AuthService.create_access_token({"sub": user.id, "username": user.username})
    return Token(access_token=token, user=UserResponse.model_validate(user))


# 用户登录：验证用户名和密码，返回JWT令牌
@router.post("/login", response_model=Token)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await AuthService.authenticate_user(db, data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = AuthService.create_access_token({"sub": user.id, "username": user.username})
    return Token(access_token=token, user=UserResponse.model_validate(user))