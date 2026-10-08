from pydantic import BaseModel

from schemas.user import UserOut


class TokenOut(BaseModel):
    """登录成功返回：JWT + 用户信息"""

    access_token: str
    token_type: str = "bearer"
    user: UserOut
