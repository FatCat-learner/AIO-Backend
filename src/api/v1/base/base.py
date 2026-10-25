from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import decode_token
from models.users import User

# 告诉 FastAPI 从请求头 Authorization: Bearer <token> 取 token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """公共依赖：获取当前登录用户。
    任何需要登录的路由都可以 Depends(get_current_user)"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效或过期的登录凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except Exception as err:
        raise credentials_exception from err

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    return user


# 可选登录：动作库这类读路径未登录也能浏览，登录后才多出收藏 / 常用度语义。
# auto_error=False 让 FastAPI 在没带 Authorization 头时给 None 而不是抛 401。
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False,
)


async def get_current_user_optional(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """公共依赖：拿到登录用户就返回，没带 token / token 失效 / 用户被禁用一律当游客。

    与 get_current_user 的差别只有一点：**从不抛 401**。
    用于「游客可看、登录后个性化」的接口。
    """
    if not token:
        return None

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
    except Exception:
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return None

    return user


class Pagination:
    """公共分页依赖。用法：page: Pagination = Depends()"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        size: int = Query(20, ge=1, le=100, description="每页数量，最大 100"),
    ):
        self.page = page
        self.size = size
        self.offset = (page - 1) * size
