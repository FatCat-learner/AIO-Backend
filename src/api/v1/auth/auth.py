from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.auth import codes
from core.database import get_db
from core.responses import success_response
from core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from models.users import User
from schemas.auth import (
    CodeLoginIn,
    CodeSendIn,
    CodeSendOut,
    OAuthLoginIn,
    ResetPasswordIn,
    TokenOut,
)
from schemas.base import IResponse
from schemas.user import UserOut, UserRegister

# 注意：prefix 在 v1/__init__.py 里统一加，这里只写具体路径
router = APIRouter()


async def _find_by_account(db: AsyncSession, account: str) -> User | None:
    result = await db.execute(select(User).where(User.username == account))
    return result.scalar_one_or_none()


def _token_payload(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(subject=user.id),
        user=UserOut.model_validate(user),
    )


@router.post(
    "/code/send",
    response_model=IResponse[CodeSendOut],
    summary="发送验证码（开发期后端模拟，直接把码返回给前端）",
)
async def send_code(payload: CodeSendIn):
    account = payload.account.strip()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请填写手机号或邮箱",
        )

    code = codes.issue_code(payload.scene, account)
    return success_response(
        CodeSendOut(code=code, expires_in=codes.CODE_TTL_SECONDS),
        message="验证码已生成（模拟）",
    )


@router.post(
    "/register",
    response_model=IResponse[UserOut],
    status_code=status.HTTP_201_CREATED,
    summary="注册新用户",
)
async def register(
    payload: UserRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = (payload.account or payload.username or "").strip()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请填写手机号或邮箱",
        )

    # 账号注册：先过验证码（开发期模拟码，校验通过即失效）
    if payload.account and payload.code:
        ok, reason = codes.verify_code("register", account, payload.code)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=reason,
            )

    # 1. 检查账号是否已存在
    if await _find_by_account(db, account):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该账号已注册，请直接登录",
        )

    # 2. 创建用户，密码哈希后存储
    user = User(
        username=account,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname or account,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)  # 从数据库刷新，拿到默认值

    # 注册接口的 HTTP 状态码为 201，响应体中的 code 与之保持一致。
    return success_response(
        UserOut.model_validate(user),
        message="注册成功",
        code=status.HTTP_201_CREATED,
    )


@router.post(
    "/login",
    response_model=IResponse[TokenOut],
    summary="登录，返回 JWT",
)
async def login(
    # OAuth2PasswordRequestForm 让 /docs 右上角 Authorize 能直接用
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. 按用户名查用户
    user = await _find_by_account(db, form.username)

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
    return success_response(_token_payload(user), message="登录成功")


@router.post(
    "/login/code",
    response_model=IResponse[TokenOut],
    summary="验证码登录",
)
async def login_by_code(
    payload: CodeLoginIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = payload.account.strip()
    user = await _find_by_account(db, account)
    if not user:
        # 不暴露「账号是否存在」以外的东西，这里明确提示未注册，前端可跳注册
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该账号还未注册",
        )

    ok, reason = codes.verify_code("login", account, payload.code)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    return success_response(_token_payload(user), message="登录成功")


@router.post(
    "/password/reset",
    response_model=IResponse[dict],
    summary="忘记密码：验证码校验通过后重设密码",
)
async def reset_password(
    payload: ResetPasswordIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = payload.account.strip()
    user = await _find_by_account(db, account)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该账号还未注册",
        )

    ok, reason = codes.verify_code("reset", account, payload.code)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    user.password_hash = hash_password(payload.password)
    db.add(user)
    await db.commit()
    codes.consume("reset", account)

    return success_response({"account": account}, message="密码已修改")


@router.post(
    "/oauth/login",
    response_model=IResponse[TokenOut],
    summary="第三方快捷登录（开发期不校验第三方 code，按 provider 建号）",
)
async def oauth_login(
    payload: OAuthLoginIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = f"{payload.provider}_demo"
    user = await _find_by_account(db, account)
    if not user:
        user = User(
            username=account,
            password_hash=hash_password(f"oauth_{payload.provider}_demo"),
            nickname=f"{payload.provider} 用户",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return success_response(_token_payload(user), message="登录成功")
