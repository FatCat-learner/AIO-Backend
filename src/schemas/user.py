from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRegister(BaseModel):
    """注册请求体

    两种用法：
    - 老接口：username + password + nickname
    - 账号注册：account_type + account + code（开发期验证码由后端模拟下发）
    username 与 account 至少给一个。
    """

    username: str | None = Field(default=None, min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    nickname: str | None = Field(default=None, max_length=50)
    account_type: str | None = Field(default=None, pattern="^(phone|email)$")
    account: str | None = Field(default=None, min_length=3, max_length=64)
    code: str | None = Field(default=None, min_length=4, max_length=8)


class UserOut(BaseModel):
    """用户响应体。绝不包含 password_hash"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    nickname: str
    created_at: datetime
