from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from models.users import User
from schemas.auth import TokenOut
from schemas.user import UserOut, UserRegister

# 注意：prefix 在 v1/__init__.py 里统一加，这里只写具体路径
router = APIRouter()


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="注册新用户",
)
async def register(
    payload: UserRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == payload.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    # 2. 创建用户，密码哈希后存储
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname or payload.username,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)  # 从数据库刷新，拿到默认值

    return user


@router.post(
    "/login",
    response_model=TokenOut,
    summary="登录，返回 JWT",
)
async def login(
    # OAuth2PasswordRequestForm 让 /docs 右上角 Authorize 能直接用
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. 按用户名查用户
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()

    # 2. 校验密码
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    # 3. 生成 JWT，sub 放用户 ID
    access_token = create_access_token(subject=user.id)

    return TokenOut(
        access_token=access_token,
        user=UserOut.model_validate(user),
    )
